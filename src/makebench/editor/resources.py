"""Biblioteca local de imagens com uso, substituição e preservação para desfazer."""

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFileDialog, QInputDialog, QListWidgetItem, QMessageBox
from makebench.core.project import ProjectError


class ResourceMixin:
    """Opera somente recursos locais do documento; nunca importa código de projeto."""

    def resource_usage(self, path):
        """Conta referências da composição, estados e ícone do aplicativo."""
        count = sum(1 for node in self.project.walk() if node.properties.get("source") == path)
        count += sum(
            1
            for states in self.project.states.values()
            for state in states
            for values in state.get("overrides", {}).values()
            if values.get("source") == path
        )
        count += int(self.project.application.get("icon") == path)
        return count

    def list_resources(self):
        """Lista referenciados e recursos órfãos, com miniaturas e quantidade de usos."""
        paths = self.project.asset_paths() | set(self.assets._cache)
        if self.assets.root:
            folder = self.assets.root / "assets"
            if folder.is_dir():
                for number, path in enumerate(folder.rglob("*")):
                    if number > 2000:
                        break
                    if path.is_file():
                        paths.add(path.relative_to(self.assets.root).as_posix())
        paths -= getattr(self.assets, "removed", set()) - self.project.asset_paths()
        for path in sorted(paths):
            uses = self.resource_usage(path)
            name = (
                next(
                    (
                        node.properties.get("image_name")
                        for node in self.project.walk()
                        if node.properties.get("source") == path
                        and node.properties.get("image_name")
                    ),
                    None,
                )
                or Path(path).name
            )
            item = QListWidgetItem(f"Imagem · {name}\nUsada em {uses} lugar(es)")
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, {"kind": "resource", "path": path})
            try:
                image = QPixmap()
                image.loadFromData(self.assets.read(path))
                if not image.isNull():
                    item.setIcon(QIcon(image))
            except (OSError, ProjectError):
                item.setText("Recurso ausente · " + name)
            self.data_list.addItem(item)

    def edit_resource(self, path):
        """Escolhe substituir ou remover apenas quando não há uso atual."""
        actions = ["Substituir em todos os lugares"]
        if self.resource_usage(path) == 0:
            actions.append("Remover recurso sem uso")
        choice, ok = QInputDialog.getItem(
            self, "Recurso do projeto", Path(path).name, actions, 0, False
        )
        if not ok:
            return
        if choice.startswith("Remover"):
            self.remove_resource(path)
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Substituir imagem", "", "Imagens (*.png *.jpg *.jpeg *.webp *.svg)"
        )
        if not filename:
            return
        try:
            new_path = self.assets.import_image(Path(filename))
        except (OSError, ProjectError) as exc:
            self._show_error(str(exc))
            return

        def replace():
            """Atualiza referências ao recurso sem apagar o arquivo original."""
            for node in self.project.walk():
                if node.properties.get("source") == path:
                    node.properties.update(source=new_path, image_name=Path(filename).name)
            for states in self.project.states.values():
                for state in states:
                    for values in state.get("overrides", {}).values():
                        if values.get("source") == path:
                            values.update(source=new_path, image_name=Path(filename).name)
            app = self.project.application
            if app.get("icon") == path:
                app["icon"] = new_path

        self._edit(replace)

    def remove_resource(self, path):
        """Remove um órfão; o cache mantém bytes necessários ao histórico da sessão."""
        if self.resource_usage(path):
            self.statusBar().showMessage("Este recurso ainda é usado pelo aplicativo.", 6000)
            return
        try:
            self.assets.read(path)
            if self.assets.root:
                file = self.assets._inside(self.assets.root, path)
                if file.exists():
                    file.unlink()
            if not hasattr(self.assets, "removed"):
                self.assets.removed = set()
            self.assets.removed.add(path)
            self._data_signature = None
            self.sync_studio()
        except (OSError, ProjectError) as exc:
            self._show_error(str(exc))
