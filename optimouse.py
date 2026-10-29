#!/usr/bin/env python3
"""OptiMouse: cursor accessibility settings for Omarchy/Hyprland."""
import hashlib, json, os, re, shutil, struct, subprocess, sys, time, tempfile, threading
from pathlib import Path

HOME=Path.home()
CONFIG=HOME/'.config/optimouse'
SETTINGS=CONFIG/'settings.json'
ICONS=HOME/'.local/share/icons'
HYPR=HOME/'.config/hypr'
PERSIST=HOME/'.local/state/omarchy/toggles/hypr/zz-optimouse.lua'
PLUGIN_ID='io.github.robbieuk1.optimouse-shake'
PLUGIN_DIR=HOME/'.config/omarchy/plugins'/PLUGIN_ID
BRIDGE_PID=HOME/'.local/state/optimouse/bridge.pid'
APP_VERSION='0.2.6'
DEFAULT={'size':32,'color':'#71FACC','follow_theme':True,'shake':False,'shake_scale':2.2,'shake_max':160,'sensitivity':2.5}

def run(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, timeout=8, **kwargs)

def read_settings():
    try: return {**DEFAULT,**json.loads(SETTINGS.read_text())}
    except (OSError,ValueError): return DEFAULT.copy()

def write_settings(data):
    CONFIG.mkdir(parents=True, exist_ok=True)
    # Replace atomically so the Quickshell file watcher sees a complete JSON file.
    payload=json.dumps(data,indent=2)+'\n'
    fd,name=tempfile.mkstemp(prefix='.settings-',dir=CONFIG)
    try:
        with os.fdopen(fd,'w') as handle:
            handle.write(payload)
        os.replace(name,SETTINGS)
    finally:
        if os.path.exists(name): os.unlink(name)

def base_theme():
    for name in ('Adwaita','default','Bibata-Modern-Classic','breeze_cursors'):
        for root in (Path('/usr/share/icons'), ICONS, HOME/'.icons'):
            p=root/name/'cursors'
            if p.is_dir() and any(p.iterdir()): return p
    raise RuntimeError('No system XCursor theme found. Install adwaita-cursors.')

def tint_xcursor(raw, rgb):
    """Recolour light cursor pixels while retaining shadows, antialiasing and animations."""
    data=bytearray(raw)
    if len(data)<16 or data[:4]!=b'Xcur': return raw
    _,_,n=struct.unpack_from('<III',data,4)
    if n>10000: return raw
    tr,tg,tb=rgb
    # Cursor artwork reuses a small palette of opaque/antialiased RGB values.
    # Cache each recolour once instead of recalculating luminance and mixing
    # three channels for every pixel in every animation frame.
    palette={}
    for i in range(n):
        off=16+i*12
        if off+12>len(data): break
        typ,_,pos=struct.unpack_from('<III',data,off)
        if typ!=0xfffd0002 or pos+36>len(data): continue
        header,chunk_typ,_,_,width,height,_,_,_=struct.unpack_from('<IIIIIIIII',data,pos)
        if chunk_typ!=typ or width*height>4_000_000: continue
        start=pos+header
        if header<36 or start+width*height*4>len(data): continue
        stop=start+width*height*4
        if sys.byteorder=='little':
            # On Omarchy's x86-64 machines, a 32-bit memoryview allows one
            # read and one write per pixel, instead of four Python byte
            # operations. Keep the alpha byte unchanged; this produces
            # byte-for-byte identical cursor images to the previous code.
            pixels=memoryview(data)[start:stop].cast('I')
            for index,value in enumerate(pixels):
                if not (value & 0xff000000):
                    continue
                tinted=palette.get(value)
                if tinted is None:
                    b,g,r=value & 255,(value >> 8) & 255,(value >> 16) & 255
                    lum=(r*299+g*587+b*114)//1000
                    w=min(1,max(0,(lum-35))/220)
                    tinted=((value & 0xff000000)
                            | round(b*(1-w)+tb*w)
                            | (round(g*(1-w)+tg*w) << 8)
                            | (round(r*(1-w)+tr*w) << 16))
                    palette[value]=tinted
                pixels[index]=tinted
            pixels.release()
        else:
            # XCursor pixels are always little-endian BGRA, even when
            # Python runs on a big-endian system.
            for j in range(start,stop,4):
                if data[j+3]==0:
                    continue
                b,g,r=data[j],data[j+1],data[j+2]
                key=(b,g,r)
                tinted=palette.get(key)
                if tinted is None:
                    lum=(r*299+g*587+b*114)//1000
                    w=min(1,max(0,(lum-35))/220)
                    tinted=(round(b*(1-w)+tb*w),
                            round(g*(1-w)+tg*w),
                            round(r*(1-w)+tr*w))
                    palette[key]=tinted
                data[j],data[j+1],data[j+2]=tinted
    return bytes(data)

def source_signature(source):
    """Fingerprint file names, sizes, and mtimes without reading large cursors."""
    entries=[]
    for entry in source.iterdir():
        stat=entry.lstat()
        entries.append((entry.name,stat.st_size,stat.st_mtime_ns))
    payload=json.dumps(sorted(entries),separators=(',',':')).encode()
    return hashlib.sha256(payload).hexdigest()

def create_theme(color):
    source=base_theme()
    target=ICONS/('OptiMouse-'+color.lstrip('#').upper())
    dst=target/'cursors'
    stamp=target/'.optimouse-cache.json'
    signature=source_signature(source)
    # A colour used before is safe to reuse if the source files haven't
    # changed and all of the expected theme entries are still present.
    try:
        meta=json.loads(stamp.read_text())
        if (meta.get('version')==1 and meta.get('source')==str(source)
                and meta.get('signature')==signature
                and dst.is_dir() and (target/'index.theme').is_file()
                and all((dst/entry.name).exists() or (dst/entry.name).is_symlink()
                        for entry in source.iterdir())):
            return target.name
    except (OSError,ValueError,TypeError,AttributeError):
        pass

    dst.mkdir(parents=True, exist_ok=True)
    # Invalidate an old stamp before modifying files. A failed generation must
    # never look complete to a future Apply.
    stamp.unlink(missing_ok=True)
    rgb=tuple(int(color[i:i+2],16) for i in (1,3,5))
    for entry in source.iterdir():
        output=dst/entry.name
        if output.exists() or output.is_symlink(): output.unlink()
        if entry.is_symlink():
            link=os.readlink(entry)
            if not os.path.isabs(link): output.symlink_to(link)
            else:
                try: output.write_bytes(tint_xcursor(entry.resolve().read_bytes(),rgb))
                except OSError: pass
        elif entry.is_file(): output.write_bytes(tint_xcursor(entry.read_bytes(),rgb))
    (target/'index.theme').write_text('[Icon Theme]\nName=OptiMouse Custom\nComment=Cursor palette generated by OptiMouse\nInherits=Adwaita\n')
    stamp.write_text(json.dumps({'version':1,'source':str(source),'signature':signature})+'\n')
    return target.name


_THEME_BUILD_LOCK=threading.Lock()

def prepare_custom_theme(color):
    """Build cursor files without changing active desktop settings."""
    with _THEME_BUILD_LOCK:
        return create_theme(color)


def current_theme():
    for k in ('HYPRCURSOR_THEME','XCURSOR_THEME'):
        v=os.environ.get(k)
        if v and v!='OptiMouse-Custom': return v
    try:
        r=run(['gsettings','get','org.gnome.desktop.interface','cursor-theme'])
        value=r.stdout.strip().strip("'\"")
        if value and value!='OptiMouse-Custom': return value
    except (OSError,subprocess.TimeoutExpired): pass
    return 'Adwaita'

def is_generated(name):
    return name.startswith('OptiMouse-')

def desktop_theme():
    # Environment variables are normally inherited from the login session,
    # and are more useful for theme-following than GTK's last custom theme.
    def available(value):
        if not value or is_generated(value) or not re.fullmatch(r'[A-Za-z0-9._+-]{1,128}',value):
            return False
        for root in (HOME/'.local/share/icons',HOME/'.icons',Path('/usr/share/icons')):
            if (root/value/'cursors').is_dir() or (root/value/'hyprcursors').is_dir():
                return True
        return False
    for key in ('HYPRCURSOR_THEME','XCURSOR_THEME'):
        value=os.environ.get(key,'')
        if available(value): return value
    if shutil.which('gsettings'):
        result=run(['gsettings','get','org.gnome.desktop.interface','cursor-theme'])
        value=result.stdout.strip().strip("'\"")
        if available(value): return value
    for value in ('Adwaita','default','Bibata-Modern-Classic'):
        if available(value): return value
    raise RuntimeError('No usable theme cursor was found to follow')


def persist_cursor(theme,size,follow):
    PERSIST.parent.mkdir(parents=True,exist_ok=True)
    if follow:
        # Leave theme choice to Omarchy; retain just the requested size.
        lines=[f'hl.env("HYPRCURSOR_SIZE", "{size}")',
               f'hl.env("XCURSOR_SIZE", "{size}")']
    else:
        if not re.fullmatch(r'[A-Za-z0-9_.+-]{1,128}',theme):
            raise ValueError('Invalid cursor theme name')
        lines=[f'hl.env("HYPRCURSOR_THEME", "{theme}")',
               f'hl.env("XCURSOR_THEME", "{theme}")',
               f'hl.env("HYPRCURSOR_SIZE", "{size}")',
               f'hl.env("XCURSOR_SIZE", "{size}")']
    payload='-- OptiMouse cursor overrides; loaded by Omarchy toggles\n'+'\n'.join(lines)+'\n'
    fd,name=tempfile.mkstemp(prefix='.optimouse-',dir=PERSIST.parent)
    try:
        with os.fdopen(fd,'w') as handle: handle.write(payload)
        os.replace(name,PERSIST)
    finally:
        if os.path.exists(name): os.unlink(name)

def update_gtk_settings_ini(content,theme,size):
    """Update only GTK cursor keys, preserving unrelated settings and sections."""
    keys=('gtk-cursor-theme-name','gtk-cursor-theme-size')
    updates=('gtk-cursor-theme-name='+theme,'gtk-cursor-theme-size='+str(size))
    lines=content.splitlines()
    output=[]
    inside=False
    found=False
    inserted=False
    for line in lines:
        stripped=line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            if inside and not inserted:
                output.extend(updates)
                inserted=True
            inside=stripped.lower()=='[settings]'
            if inside:
                found=True
                inserted=False
        if inside and any(stripped.startswith(key+'=') or
                          stripped.startswith(key+' =') for key in keys):
            continue
        output.append(line)
    if not found:
        if output and output[-1].strip():
            output.append('')
        output.append('[Settings]')
        output.extend(updates)
    elif inside and not inserted:
        output.extend(updates)
    return '\n'.join(output)+'\n'

def sync_gtk_cursor_settings(theme,size):
    """Synchronise GTK3/GTK4 cursor settings without rewriting other options.

    Oma Cursor Style also writes both settings.ini files. OptiMouse retains
    its Omarchy toggle persistence rather than editing hyprland.lua itself.
    """
    for version in ('gtk-3.0','gtk-4.0'):
        path=HOME/'.config'/version/'settings.ini'
        original=path.read_text() if path.exists() else ''
        updated=update_gtk_settings_ini(original,theme,size)
        if updated==original:
            continue
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,temp_path=tempfile.mkstemp(prefix='.optimouse-gtk-',dir=path.parent)
        try:
            with os.fdopen(fd,'w') as handle:
                handle.write(updated)
            os.replace(temp_path,path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

def checked(command,label):
    result=run(command)
    if result.returncode:
        raise RuntimeError(label+': '+(result.stderr.strip() or result.stdout.strip() or 'command failed'))
    return result

def apply(data):
    """Apply cursor settings; return phase durations for troubleshooting."""
    phases={}
    checkpoint=time.monotonic()
    size=max(16,min(128,int(data['size'])))
    follow=bool(data['follow_theme'])
    theme=desktop_theme() if follow else prepare_custom_theme(data['color'])
    phases['theme']=time.monotonic()-checkpoint
    if not shutil.which('hyprctl'):
        raise RuntimeError('hyprctl is unavailable')
    checkpoint=time.monotonic()
    persist_cursor(theme,size,follow)
    phases['save']=time.monotonic()-checkpoint
    checkpoint=time.monotonic()
    checked(['hyprctl','setcursor',theme,str(size)],'Cursor apply')
    phases['hyprland']=time.monotonic()-checkpoint
    checkpoint=time.monotonic()
    if shutil.which('gsettings'):
        checked(['gsettings','set','org.gnome.desktop.interface','cursor-theme',theme],'GTK cursor theme')
        checked(['gsettings','set','org.gnome.desktop.interface','cursor-size',str(size)],'GTK cursor size')
    sync_gtk_cursor_settings(theme,size)
    phases['gtk']=time.monotonic()-checkpoint
    checkpoint=time.monotonic()
    # Reuse the already proven Shake Preview path. Do not change the shake
    # service, move the mouse, or perform a compositor-wide reload.
    refreshed=overlay_running()
    if refreshed:
        write_settings({**data, 'preview_token':str(time.time_ns())})
    else:
        write_settings(data)
    phases['preview']=time.monotonic()-checkpoint
    return theme,refreshed,phases


def overlay_running():
    """Check that the Quickshell service actually started its cursor bridge."""
    try:
        pid=int(BRIDGE_PID.read_text().strip())
        if pid<=0:
            return False
        command=(Path('/proc')/str(pid)/'cmdline').read_bytes()
        return b'cursor-bridge.py' in command
    except (ValueError,OSError):
        return False

def diagnostics():
    print('OptiMouse diagnostics; Hyprland 0.56')
    for command in (['hyprctl','version'],['hyprctl','-j','cursorpos'],
                    ['gsettings','get','org.gnome.desktop.interface','cursor-theme'],
                    ['omarchy','plugin','list']):
        try:
            result=run(command)
            print(' '.join(command), 'exit',result.returncode)
            print(result.stdout[:900],result.stderr[:500])
        except Exception as error: print(str(error))
    print('Plugin path:',PLUGIN_DIR,'exists:',PLUGIN_DIR.exists())
    print('Overlay bridge active:',overlay_running())
    print('Toggle path:',PERSIST,'exists:',PERSIST.exists())


CSS='''
window { background: #000000; color: #e7f5f0; }
headerbar { background: #000000; border-bottom: 1px solid #21443c; }
label { color: #e7f5f0; }
button { background: #1a302b; color: #d7fdef; border: 1px solid #305a50; border-radius: 10px; padding: 10px; }
button.suggested-action { background: #6ef4c0; color: #081610; font-weight: 700; }
scale highlight { background: #6ef4c0; }
switch:checked { background: #6ef4c0; }
.card { background: #101a18; padding: 18px; border: 1px solid #27453c; border-radius: 12px; }
.heading { font-size: 18px; font-weight: 700; color: #8cf8d1; }
.hint { color: #a8c5ba; }
'''

def gui():
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,Gdk,GLib
    import threading

    initial=read_settings()
    win=Gtk.Window(title='OptiMouse '+APP_VERSION)
    win.set_default_size(625,665)
    win.set_border_width(18)
    win.connect('destroy',Gtk.main_quit)
    provider=Gtk.CssProvider()
    provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
    win.add(root)

    def label(value,style=None):
        item=Gtk.Label(label=value,xalign=0)
        if style: item.get_style_context().add_class(style)
        return item

    root.pack_start(label('OptiMouse  •  Pointer accessibility   v'+APP_VERSION,'heading'),False,False,2)
    normal=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
    normal.get_style_context().add_class('card')
    root.pack_start(normal,False,False,0)
    normal.pack_start(label('Normal pointer size','heading'),False,False,0)
    size=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,16,128,4)
    size.set_digits(0);size.set_value(initial['size'])
    size.set_value_pos(Gtk.PositionType.RIGHT)
    normal.pack_start(size,False,False,0)
    follow=Gtk.CheckButton(label='Follow Omarchy desktop cursor style')
    follow.set_active(initial['follow_theme'])
    normal.pack_start(follow,False,False,0)
    color_row=Gtk.Box(spacing=12)
    # Gtk.ColorButton creates its own popup, which has been positioned at the
    # desktop's top-left on this Hyprland setup. Use a regular button and an
    # explicitly parented, modal chooser dialog instead.
    colour_state={'rgba':Gdk.RGBA()}
    colour_state['rgba'].parse(initial['color'])
    chooser=Gtk.Button()
    chooser.set_tooltip_text('Choose pointer colour')
    chooser_contents=Gtk.Box(spacing=8)
    swatch=Gtk.DrawingArea()
    swatch.set_size_request(54,28)
    chooser_contents.pack_start(swatch,False,False,0)
    chooser_contents.pack_start(Gtk.Label(label='Choose…'),False,False,0)
    chooser.add(chooser_contents)

    def draw_swatch(widget,cr):
        allocation=widget.get_allocation()
        cr.set_source_rgb(0.15,0.20,0.18)
        cr.rectangle(0,0,allocation.width,allocation.height)
        cr.fill()
        Gdk.cairo_set_source_rgba(cr,colour_state['rgba'])
        cr.rectangle(2,2,max(0,allocation.width-4),max(0,allocation.height-4))
        cr.fill()
        return False

    swatch.connect('draw',draw_swatch)

    def choose_colour(*_):
        dialog=Gtk.ColorChooserDialog(title='Choose pointer colour')
        dialog.set_transient_for(win)
        dialog.set_modal(True)
        dialog.set_destroy_with_parent(True)
        dialog.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        dialog.set_use_alpha(False)
        dialog.set_rgba(colour_state['rgba'])
        try:
            if dialog.run()==Gtk.ResponseType.OK:
                colour_state['rgba']=dialog.get_rgba()
                swatch.queue_draw()
                queue_colour_preload()
        finally:
            dialog.destroy()

    chooser.connect('clicked',choose_colour)
    color_row.pack_start(chooser,False,False,0)
    color_row.pack_start(label('Pointer colour / enlarged pointer outline'),True,True,0)
    normal.pack_start(color_row,False,False,0)
    color_hint=label('', 'hint')
    normal.pack_start(color_hint,False,False,0)
    def sync_color(*_):
        color_hint.set_text(
            'Following Omarchy theme: this colour changes the shake pointer outline only.'
            if follow.get_active() else
            'Custom mode: this colour controls the normal pointer and shake outline.')
    follow.connect('toggled',sync_color)
    sync_color()
    preparation=label('Colour preparation: not started', 'hint')
    preparation.set_line_wrap(True)
    normal.pack_start(preparation,False,False,0)
    preloader={'request':0}

    def staged_colour():
        c=colour_state['rgba']
        return '#%02X%02X%02X'%(round(c.red*255),round(c.green*255),round(c.blue*255))

    def queue_colour_preload(*_):
        preloader['request']+=1
        request=preloader['request']
        if follow.get_active():
            preparation.set_text('Follow theme: colour staged for enlarged pointer. Apply to save.')
            return
        colour=staged_colour()
        preparation.set_text('Preparing '+colour+' in background…')

        def worker():
            try:
                prepare_custom_theme(colour)
                outcome='Ready: '+colour+' — press Apply to change the pointer.'
            except Exception as error:
                outcome='Preparation failed: '+str(error)

            def show_result():
                if request==preloader['request'] and not follow.get_active():
                    preparation.set_text(outcome)
                return False

            GLib.idle_add(show_result)

        threading.Thread(target=worker,daemon=True).start()

    follow.connect('toggled',queue_colour_preload)

    shake_card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
    shake_card.get_style_context().add_class('card')
    root.pack_start(shake_card,False,False,0)
    shake=Gtk.CheckButton(label='Shake to find — temporarily enlarge pointer')
    shake.set_active(initial.get('shake',False))
    shake_card.pack_start(shake,False,False,0)
    shake_card.pack_start(label('Maximum shake pointer size','heading'),False,False,0)
    shake_max=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,32,256,8)
    shake_max.set_digits(0);shake_max.set_value(initial.get('shake_max',160))
    shake_max.set_value_pos(Gtk.PositionType.RIGHT)
    shake_card.pack_start(shake_max,False,False,0)
    sensitivity_row=Gtk.Box(spacing=12)
    sensitivity_row.pack_start(label('Shake sensitivity'),True,True,0)
    sensitivity=Gtk.ComboBoxText()
    for text in ('Light','Medium','Hard'): sensitivity.append_text(text)
    levels=[2.0,2.5,3.5]
    nearest=min(range(len(levels)),key=lambda i:abs(levels[i]-float(initial.get('sensitivity',2.5))))
    sensitivity.set_active(nearest)
    sensitivity_row.pack_end(sensitivity,False,False,0)
    shake_card.pack_start(sensitivity_row,False,False,0)
    preview=Gtk.Button(label='Preview enlarged pointer')
    shake_card.pack_start(preview,False,False,0)

    status=label('Ready. Use Apply settings to save cursor preferences.','hint')
    status.set_line_wrap(True)
    # Prevent long GTK labels from asking for a window wider than the screen.
    status.set_max_width_chars(66)
    root.pack_start(status,False,False,0)
    row=Gtk.Box(spacing=10)
    root.pack_end(row,False,False,0)
    reset=Gtk.Button(label='Restore defaults')
    row.pack_start(reset,False,False,0)
    apply_btn=Gtk.Button(label='Apply settings')
    apply_btn.get_style_context().add_class('suggested-action')
    row.pack_end(apply_btn,False,False,0)
    # Keep total and component timings visible in the settings window.
    timing=label('Apply time: —','heading')
    row.pack_end(timing,False,False,12)
    breakdown=label('Timing: not measured yet', 'hint')
    breakdown.set_line_wrap(True)
    breakdown.set_max_width_chars(80)
    root.pack_end(breakdown,False,False,3)

    def collect():
        c=colour_state['rgba']
        color='#%02X%02X%02X'%(round(c.red*255),round(c.green*255),round(c.blue*255))
        return {**read_settings(),'size':int(size.get_value()),'color':color,
                'follow_theme':follow.get_active(),'shake':shake.get_active(),
                'shake_max':int(shake_max.get_value()),
                'sensitivity':levels[max(0,sensitivity.get_active())]}

    def apply_clicked(*_):
        options=collect()
        started=time.monotonic()
        apply_btn.set_sensitive(False)
        apply_btn.set_label('Applying…')
        timing.set_text('Apply time: measuring…')
        status.set_text('Applying cursor settings…')

        def finish(message,seconds,phases):
            apply_btn.set_label('Apply settings')
            apply_btn.set_sensitive(True)
            timing.set_text(f'Apply time: {seconds:.2f} s')
            status.set_text(message)
            if phases:
                breakdown.set_text(
                    'Theme {:.2f}s  •  Save {:.2f}s  •  Hyprland {:.2f}s  •  GTK {:.2f}s  •  Preview {:.2f}s'.format(
                        *(phases.get(key,0.0) for key in
                          ('theme','save','hyprland','gtk','preview'))))
            else:
                breakdown.set_text('Phase timings unavailable — see error above.')
            return False

        def worker():
            phases={}
            try:
                theme,refreshed,phases=apply(options)
                message=f'Applied {theme} at {options["size"]} px.'
                if refreshed:
                    message+=' Pointer refresh requested.'
                else:
                    message+=' Overlay unavailable for refresh.'
                if not PLUGIN_DIR.exists():
                    message+=' Shake overlay not installed.'
                elif not overlay_running():
                    message+=' Shake overlay not running.'
            except Exception as error:
                message='Unable to apply: '+str(error)
            GLib.idle_add(finish,message,time.monotonic()-started,phases)

        threading.Thread(target=worker,daemon=True).start()

    def preview_clicked(*_):
        if not PLUGIN_DIR.exists():
            status.set_text('Shake overlay is not installed. Run the updated one-line installer.')
            return
        if not overlay_running():
            status.set_text('Shake overlay is not running. Run: omarchy restart shell — then try Preview again.')
            return
        options=collect()
        options['preview_token']=str(time.time_ns())
        try:
            write_settings(options)
            status.set_text('Preview requested — watch the pointer for the grow-and-shrink animation.')
        except Exception as error:
            status.set_text('Preview failed: '+str(error))

    def reset_clicked(*_):
        size.set_value(DEFAULT['size'])
        follow.set_active(DEFAULT['follow_theme'])
        shake.set_active(DEFAULT['shake'])
        shake_max.set_value(DEFAULT['shake_max'])
        sensitivity.set_active(1)
        colour_state['rgba'].parse(DEFAULT['color'])
        swatch.queue_draw()
        queue_colour_preload()
        status.set_text('Defaults selected. Press Apply settings to save.')

    apply_btn.connect('clicked',apply_clicked)
    preview.connect('clicked',preview_clicked)
    reset.connect('clicked',reset_clicked)
    win.show_all()
    # Warm the existing custom selection without changing the live pointer.
    queue_colour_preload()
    Gtk.main()

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--version': print('OptiMouse',APP_VERSION)
    elif len(sys.argv)>1 and sys.argv[1]=='--diagnose': diagnostics()
    elif len(sys.argv)>1 and sys.argv[1]=='--apply':
        print('Applied cursor theme:',apply(read_settings()))
    else: gui()
