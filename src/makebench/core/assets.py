"""Armazenamento de recursos sem dependência de toolkit gráfico."""
import hashlib
import os
from pathlib import Path,PurePosixPath
import tempfile
import xml.etree.ElementTree as ET
from .storage import StorageError


class AssetStore:
    """Cache portátil de imagens, com caminhos confinados e publicação exclusiva."""
    def __init__(self,root=None):
        """Associa uma pasta opcional; importações permanecem em memória até salvar."""
        self.root=Path(root).resolve() if root else None;self._cache={}

    @staticmethod
    def inside(root,name):
        """Recusa traversal, caminhos absolutos e links que escapem da pasta."""
        parts=PurePosixPath(name);root=Path(root).resolve()
        if parts.is_absolute() or '..' in parts.parts or '\\' in name or len(parts.parts)<2 or parts.parts[0]!='assets':raise StorageError('O recurso precisa ficar dentro de assets.')
        path=(root/name).resolve()
        if not path.is_relative_to(root):raise StorageError('O recurso aponta para fora do projeto.')
        return path

    def import_image(self,path):
        """Identifica imagens estáticas por assinatura; o frontend valida a decodificação."""
        path=Path(path);data=path.read_bytes()
        if len(data)>50*1024*1024:raise StorageError('A imagem excede 50 MB.')
        if data.startswith(b'\x89PNG\r\n\x1a\n'):extension='png'
        elif data.startswith(b'\xff\xd8\xff'):extension='jpg'
        elif data[:4]==b'RIFF' and data[8:12]==b'WEBP':extension='webp'
        else:
            try:
                if ET.fromstring(data).tag.split('}')[-1]!='svg':raise ValueError()
                extension='svg'
            except (ET.ParseError,ValueError):raise StorageError('Escolha PNG, JPEG, WebP ou SVG válido.')
        name=f'assets/{hashlib.sha256(data).hexdigest()}.{extension}';self._cache[name]=data;return name

    def read(self,name):
        """Resolve só recursos da pasta do projeto ou importados explicitamente."""
        if name not in self._cache:
            if self.root is None:raise StorageError('Recurso não encontrado: '+name)
            self._cache[name]=self.inside(self.root,name).read_bytes()
        return self._cache[name]

    def write_referenced(self,root,names):
        """Copia recursos sem sobrescrever outro conteúdo; mantém cache para desfazer."""
        for name in sorted(names):
            data=self.read(name);target=self.inside(root,name)
            if target.exists():
                if target.read_bytes()!=data:raise StorageError('O destino contém outro recurso: '+name)
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as stream:
                stream.write(data);stream.flush();os.fsync(stream.fileno());temporary=Path(stream.name)
            try:os.link(temporary,target)
            finally:temporary.unlink(missing_ok=True)
