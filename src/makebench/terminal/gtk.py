"""Terminal GTK4 com a mesma PTY e emulação utilizadas no editor Qt."""
from .session import TerminalSession, color, key_input


def create_terminal(root=None):
    """Cria uma superfície GTK inerte; o runtime decide quando iniciar o processo."""
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, Gdk, GLib, Pango
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    scroll = Gtk.ScrolledWindow(min_content_height=140, hexpand=True, vexpand=True)
    view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.NONE)
    scroll.set_child(view); box.append(scroll)
    session = TerminalSession(root=root); box.terminal = session
    buffer = view.get_buffer(); tags = {}; state = {'revision':-1, 'timer':None, 'size':None,'rows':[],'cache':{},'screen_ids':set()}
    buffer.set_text('Terminal · prévia inativa')

    def refresh():
        """Aplica saída ANSI somente quando muda, preservando seleção e rolagem."""
        context = view.get_pango_context(); metrics = context.get_metrics(None, None)
        cw = max(1, metrics.get_approximate_char_width()/Pango.SCALE)
        ch = max(1, (metrics.get_ascent()+metrics.get_descent())/Pango.SCALE)
        size = (max(2, int(scroll.get_width()/cw)-1), max(2, int(scroll.get_height()/ch)))
        if size != state['size'] and scroll.get_width() > 1:
            state['size'] = size; session.resize(*size)
        revision = session.poll()
        if revision != state['revision']:
            state['revision'] = revision
            bar = scroll.get_vadjustment(); follow = bar.get_value()+bar.get_page_size() >= bar.get_upper()-ch*2
            lines = session.lines(); columns = session.screen.columns
            cache=state['cache']
            for identifier in state['screen_ids']:cache.pop(identifier,None)
            rows=[]
            for line in lines:
                cached=cache.get(id(line))
                if cached is None or cached[1]!=columns:
                    text=''.join(line[x].data for x in range(columns))+'\n';runs=[];start=0;offset=0
                    while start<columns:
                        cell=line[start];end=start+1
                        style=(cell.fg,cell.bg,cell.bold,cell.italics,cell.underscore,cell.reverse)
                        while end<columns:
                            other=line[end]
                            if (other.fg,other.bg,other.bold,other.italics,other.underscore,other.reverse)!=style:break
                            end+=1
                        length=len(''.join(line[x].data for x in range(start,end)))
                        if style!=('default','default',False,False,False,False):runs.append((offset,offset+length,style))
                        offset+=length;start=end
                    data=(text,tuple(runs));cache[id(line)]=(line,columns,data)
                else:data=cached[2]
                rows.append(data)
            state['screen_ids']={id(line) for line in lines[-session.screen.lines:]}
            if len(cache)>11000:
                identifiers={id(line) for line in lines}
                state['cache']={key:value for key,value in cache.items() if key in identifiers}
            previous=state['rows'];prefix=0
            while prefix<min(len(previous),len(rows)) and previous[prefix]==rows[prefix]:prefix+=1
            suffix=0
            while suffix<min(len(previous),len(rows))-prefix and previous[-1-suffix]==rows[-1-suffix]:suffix+=1
            if not previous:buffer.set_text('')
            first=sum(len(row[0]) for row in previous[:prefix])
            last=sum(len(row[0]) for row in previous[:len(previous)-suffix])
            buffer.delete(buffer.get_iter_at_offset(first),buffer.get_iter_at_offset(last))
            changed=rows[prefix:len(rows)-suffix if suffix else len(rows)]
            buffer.insert(buffer.get_iter_at_offset(first),''.join(row[0] for row in changed))
            offset=first
            for text,runs in changed:
                for first_run,last_run,style in runs:
                    tag=tags.get(style)
                    if tag is None and len(tags)<4096:
                        fg,bg,bold,italics,underscore,reverse=style
                        options={'weight':Pango.Weight.BOLD if bold else Pango.Weight.NORMAL,
                                 'style':Pango.Style.ITALIC if italics else Pango.Style.NORMAL,
                                 'underline':Pango.Underline.SINGLE if underscore else Pango.Underline.NONE}
                        if reverse:fg,bg=bg,fg
                        if fg!='default':options['foreground']=color(fg,'#eeeeee')
                        if bg!='default':options['background']=color(bg,'#222222')
                        tag=buffer.create_tag(None,**options);tags[style]=tag
                    if tag:buffer.apply_tag(tag,buffer.get_iter_at_offset(offset+first_run),buffer.get_iter_at_offset(offset+last_run))
                offset+=len(text)
            state['rows']=rows
            cursor = session.screen.cursor
            cursor_offset = sum(len(''.join(line[x].data for x in range(columns)))+1 for line in lines[:len(lines)-session.screen.lines+cursor.y])
            cursor_offset += len(''.join(lines[len(lines)-session.screen.lines+cursor.y][x].data for x in range(cursor.x)))
            if 'cursor' in tags:buffer.remove_tag(tags['cursor'],buffer.get_start_iter(),buffer.get_end_iter())
            if session.running and not cursor.hidden:
                tag = tags.get('cursor')
                if tag is None: tag = buffer.create_tag(None, underline=Pango.Underline.SINGLE); tags['cursor'] = tag
                buffer.apply_tag(tag, buffer.get_iter_at_offset(cursor_offset), buffer.get_iter_at_offset(min(cursor_offset+1,buffer.get_char_count())))
            if follow: GLib.idle_add(lambda: bar.set_value(max(0,bar.get_upper()-bar.get_page_size())))
        if not session.running:
            state['timer'] = None; return False
        return True

    def start(program=None, arguments=None):
        """Abre processo após execução explícita; erro é retornado ao supervisor."""
        pid = session.start(program, arguments)
        if state['timer'] is None: state['timer'] = GLib.timeout_add(20, refresh)
        view.grab_focus(); return pid

    def stop():
        """Fecha PTY e jobs, removendo a fonte GLib proprietária."""
        session.stop()
        if state['timer'] is not None: GLib.source_remove(state['timer']); state['timer'] = None

    def paste(_clipboard, result):
        """Envia texto da área de transferência sem executar fora do terminal."""
        try:
            text = _clipboard.read_text_finish(result) or ''
            if 2004 << 5 in session.screen.mode: text = '\x1b[200~'+text+'\x1b[201~'
            session.send(text)
        except GLib.Error: pass

    def key(_controller, keyval, _keycode, modifiers):
        """Compartilha mapeamento VT e reserva copiar/colar com Ctrl+Shift."""
        name = Gdk.keyval_name(keyval); control = bool(modifiers & Gdk.ModifierType.CONTROL_MASK)
        if control and modifiers & Gdk.ModifierType.SHIFT_MASK:
            if name.lower() == 'c':
                bounds = buffer.get_selection_bounds()
                if bounds: view.get_clipboard().set(buffer.get_text(*bounds, True))
                return True
            if name.lower() == 'v': view.get_clipboard().read_text_async(None, paste); return True
        if modifiers & Gdk.ModifierType.SHIFT_MASK and name in {'Page_Up','Page_Down'}: return False
        character = Gdk.keyval_to_unicode(keyval)
        session.send(key_input(name, chr(character) if character else '', control, bool(modifiers & Gdk.ModifierType.ALT_MASK), 1 << 5 in session.screen.mode))
        return True

    controller = Gtk.EventControllerKey(); controller.connect('key-pressed', key); view.add_controller(controller)
    box.start_terminal = start; box.stop_terminal = stop; box.send_terminal = session.send
    box.connect('unrealize', lambda _: stop())
    return box
