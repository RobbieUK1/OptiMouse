#!/usr/bin/env python3
"""OptiMouse: cursor accessibility settings for Omarchy/Hyprland."""
import json, os, re, shutil, struct, subprocess, sys, time
from pathlib import Path

HOME=Path.home()
CONFIG=HOME/'.config/optimouse'
SETTINGS=CONFIG/'settings.json'
ICONS=HOME/'.local/share/icons'
HYPR=HOME/'.config/hypr'
PERSIST=HYPR/'optimouse.conf'
DEFAULT={'size':32,'color':'#71FACC','follow_theme':True,'shake':False,'shake_scale':2.2}
ORIGINAL=CONFIG/'original-theme.json'

def run(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, timeout=8, **kwargs)

def read_settings():
    try: return {**DEFAULT,**json.loads(SETTINGS.read_text())}
    except (OSError,ValueError): return DEFAULT.copy()

def write_settings(data):
    CONFIG.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(data,indent=2)+'\n')

def base_theme():
    for name in ('Adwaita','default','Bibata-Modern-Classic','breeze_cursors'):
        for root in (Path('/usr/share/icons'), ICONS, HOME/'.icons'):
            p=root/name/'cursors'
            if p.is_dir() and any(p.iterdir()): return p
    raise RuntimeError('No system XCursor theme found. Install adwaita-cursors.')

def render_xcursor(raw, rgb, requested_size):
    """Build an XCursor containing actual raster frames at requested_size."""
    if len(raw)<16 or raw[:4]!=b'Xcur':
        return raw
    header, version, count=struct.unpack_from('<III',raw,4)
    if header<16 or count>4096 or header+count*12>len(raw):
        return raw
    images=[]
    for i in range(count):
        typ, subtype, pos=struct.unpack_from('<III',raw,header+i*12)
        if typ!=0xfffd0002 or pos+36>len(raw):
            continue
        h,t,sub,ver,w,ht,xhot,yhot,delay=struct.unpack_from('<IIIIIIIII',raw,pos)
        if t!=typ or h<36 or not w or not ht or w*ht>2_000_000:
            continue
        start=pos+h
        if start+w*ht*4>len(raw):
            continue
        images.append((sub,w,ht,xhot,yhot,delay,raw[start:start+w*ht*4]))
    if not images:
        return raw
    # Select a single native-size animation group, then resample its frames.
    source_size=min({v[0] for v in images},key=lambda n:abs(n-32))
    selected=[v for v in images if v[0]==source_size]
    output=bytearray(b'Xcur'+struct.pack('<III',16,0x10000,len(selected)))
    offset=16+len(selected)*12
    chunks=[]
    for _,w,h,xhot,yhot,delay,pixels in selected:
        scale=requested_size/max(w,h)
        nw=max(1,round(w*scale)); nh=max(1,round(h*scale))
        nw=min(nw,512);nh=min(nh,512)
        out=bytearray(nw*nh*4)
        tr,tg,tb=rgb
        for y in range(nh):
            sy=min(h-1,int(y*h/nh))
            for x in range(nw):
                sx=min(w-1,int(x*w/nw))
                idx=(sy*w+sx)*4
                b0,g0,r0,alpha=pixels[idx:idx+4]
                # Preserve opaque black contours/shadows, tint pale body pixels.
                lum=(r0*299+g0*587+b0*114)//1000
                factor=max(0,min(1,(lum-35)/220))
                j=(y*nw+x)*4
                out[j]=round(b0*(1-factor)+tb*factor)
                out[j+1]=round(g0*(1-factor)+tg*factor)
                out[j+2]=round(r0*(1-factor)+tr*factor)
                out[j+3]=alpha
        chunk=struct.pack('<IIIIIIIII',36,0xfffd0002,requested_size,1,nw,nh,
                          min(nw-1,round(xhot*nw/w)),min(nh-1,round(yhot*nh/h)),delay)+out
        output.extend(struct.pack('<III',0xfffd0002,requested_size,offset))
        chunks.append(chunk);offset+=len(chunk)
    return bytes(output)+b''.join(chunks)

def create_theme(color,size):
    source=base_theme()
    rgb=tuple(int(color[i:i+2],16) for i in (1,3,5))
    name='OptiMouse-'+color.lstrip('#').upper()+'-'+str(size)
    target=ICONS/name
    dst=target/'cursors'
    dst.mkdir(parents=True,exist_ok=True)
    for entry in source.iterdir():
        output=dst/entry.name
        if output.exists() or output.is_symlink():output.unlink()
        if entry.is_symlink():
            link=os.readlink(entry)
            if not os.path.isabs(link) and (source/link).exists():
                output.symlink_to(link)
                continue
            src=entry.resolve()
        else:
            src=entry
        if src.is_file():
            output.write_bytes(render_xcursor(src.read_bytes(),rgb,size))
    (target/'index.theme').write_text('[Icon Theme]\nName='+name+'\nInherits=Adwaita\n')
    return name

def current_theme():
    try:
        stored=json.loads(ORIGINAL.read_text())
        candidate=stored.get('name','')
        if candidate and not candidate.startswith('OptiMouse-'):
            return candidate
    except (OSError,ValueError): pass
    for key in ('HYPRCURSOR_THEME','XCURSOR_THEME'):
        value=os.environ.get(key,'')
        if value and not value.startswith('OptiMouse-'):
            return value
    if shutil.which('gsettings'):
        res=run(['gsettings','get','org.gnome.desktop.interface','cursor-theme'])
        candidate=res.stdout.strip().strip("'\\\"")
        if candidate and not candidate.startswith('OptiMouse-'):
            return candidate
    return 'Adwaita'

def remember_original():
    if ORIGINAL.exists(): return
    name=current_theme()
    CONFIG.mkdir(parents=True,exist_ok=True)
    ORIGINAL.write_text(json.dumps({'name':name})+'\\n')

def apply(data, persist=True):
    size=max(16,min(128,int(data['size'])))
    if not data['follow_theme'] and persist:
        remember_original()
    theme=current_theme() if data['follow_theme'] else create_theme(data['color'],size)
    if persist:
        HYPR.mkdir(parents=True,exist_ok=True)
        PERSIST.write_text('# OptiMouse generated cursor settings\n'
                           f'env = XCURSOR_THEME,{theme}\n'
                           f'env = XCURSOR_SIZE,{size}\n'
                           f'env = HYPRCURSOR_THEME,{theme}\n'
                           f'env = HYPRCURSOR_SIZE,{size}\n')
    if not shutil.which('hyprctl'):
        raise RuntimeError('hyprctl is missing')
    if shutil.which('hyprctl'):
        result=run(['hyprctl','setcursor',theme,str(size)])
        if result.returncode:
            raise RuntimeError('Hyprland could not apply cursor: '+(result.stderr.strip() or result.stdout.strip()))
    if shutil.which('gsettings'):
        run(['gsettings','set','org.gnome.desktop.interface','cursor-theme',theme])
        run(['gsettings','set','org.gnome.desktop.interface','cursor-size',str(size)])
    if data['shake'] and persist and not data['follow_theme']:
        create_theme(data['color'],min(256,round(size*float(data.get('shake_scale',2.2)))))
    if shutil.which('systemctl') and persist:
        service=run(['systemctl','--user','enable','--now','optimouse-shake.service']) if data['shake'] else run(['systemctl','--user','disable','--now','optimouse-shake.service'])
        if service.returncode:
            raise RuntimeError('Shake helper: '+service.stderr.strip())
    return theme

def daemon():
    from collections import deque
    samples=deque(maxlen=18)
    boosted_until=0.0
    cooldown=0.0
    while True:
        config=read_settings()
        if not config['shake']: return
        try:
            r=run(['hyprctl','-j','cursorpos'])
            pos=json.loads(r.stdout)
            x=float(pos['x'])
            y=float(pos['y'])
            now=time.monotonic()
            samples.append((now,x,y))
            while samples and now-samples[0][0]>1.2: samples.popleft()
            if boosted_until and now>=boosted_until:
                apply(config,persist=False)
                boosted_until=0
                samples.clear()
            elif not boosted_until and now>cooldown and len(samples)>6:
                dx=[samples[i][1]-samples[i-1][1] for i in range(1,len(samples))]
                dy=[samples[i][2]-samples[i-1][2] for i in range(1,len(samples))]
                flips_x=sum(a*b<0 for a,b in zip(dx,dx[1:]) if abs(a)>10 and abs(b)>10)
                flips_y=sum(a*b<0 for a,b in zip(dy,dy[1:]) if abs(a)>10 and abs(b)>10)
                travel=sum(abs(v) for v in dx)+sum(abs(v) for v in dy)
                if max(flips_x,flips_y)>=3 and travel>=220:
                    theme=current_theme() if config['follow_theme'] else create_theme(config['color'],min(256,round(config['size']*float(config.get('shake_scale',2.2)))))
                    run(['hyprctl','setcursor',theme,str(min(256,round(config['size']*float(config.get('shake_scale',2.2)))))])
                    boosted_until=now+1.5
                    cooldown=now+3.0
                    samples.clear()
        except (OSError,ValueError,KeyError,subprocess.TimeoutExpired): pass
        time.sleep(.09)

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
    data=read_settings()
    win=Gtk.Window(title='OptiMouse')
    win.set_default_size(560,580)
    win.set_border_width(18)
    win.connect('destroy',Gtk.main_quit)
    provider=Gtk.CssProvider(); provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14)
    win.add(root)
    title=Gtk.Label(label='OptiMouse  •  Pointer accessibility',xalign=0)
    title.get_style_context().add_class('heading'); root.pack_start(title,False,False,4)
    card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
    card.get_style_context().add_class('card'); root.pack_start(card,False,False,0)
    def label(t,css=None):
        l=Gtk.Label(label=t,xalign=0)
        if css:l.get_style_context().add_class(css)
        return l
    card.pack_start(label('Pointer size','heading'),False,False,0)
    size=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,16,128,4)
    size.set_digits(0);size.set_value(data['size'])
    size.set_hexpand(True)
    size.set_value_pos(Gtk.PositionType.RIGHT)
    card.pack_start(size,False,False,0)
    follow=Gtk.CheckButton(label='Follow desktop theme cursor style')
    follow.set_active(data['follow_theme'])
    card.pack_start(follow,False,False,0)
    card.pack_start(label('Pointer colour','heading'),False,False,0)
    colors=Gtk.Box(spacing=10)
    chooser=Gtk.ColorButton()
    rgba=Gdk.RGBA();rgba.parse(data['color']);chooser.set_rgba(rgba)
    colors.pack_start(chooser,False,False,0)
    colors.pack_start(label('Choose a colour (custom cursor mode)'),True,True,0)
    card.pack_start(colors,False,False,0)
    info=label('Colour requires “Follow desktop theme” to be off.','hint')
    card.pack_start(info,False,False,0)
    def toggle_follow(*_): chooser.set_sensitive(not follow.get_active())
    follow.connect('toggled',toggle_follow);toggle_follow()
    card2=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
    card2.get_style_context().add_class('card');root.pack_start(card2,False,False,0)
    card2.pack_start(label('Shake to find','heading'),False,False,0)
    shake=Gtk.CheckButton(label='Enlarge pointer briefly when I shake the mouse')
    shake.set_active(data['shake']);card2.pack_start(shake,False,False,0)
    card2.pack_start(label('Works via a lightweight background service.','hint'),False,False,0)
    status=label('', 'hint');status.set_line_wrap(True)
    root.pack_start(status,False,False,0)
    row=Gtk.Box(spacing=10)
    root.pack_end(row,False,False,0)
    apply_btn=Gtk.Button(label='Apply settings')
    apply_btn.get_style_context().add_class('suggested-action')
    row.pack_end(apply_btn,False,False,0)
    reset=Gtk.Button(label='Restore defaults')
    row.pack_start(reset,False,False,0)
    def set_status(message): status.set_text(message)
    def apply_click(*_):
        c=chooser.get_rgba()
        color='#%02X%02X%02X'%(round(c.red*255),round(c.green*255),round(c.blue*255))
        new={'size':int(size.get_value()),'color':color,'follow_theme':follow.get_active(),'shake':shake.get_active(),'shake_scale':2.2}
        apply_btn.set_sensitive(False)
        apply_btn.set_label('Applying…')
        set_status('Applying changes to Hyprland…')
        def complete(message, ok):
            apply_btn.set_sensitive(True)
            apply_btn.set_label('Apply settings')
            set_status(message)
            if not ok:
                dialog=Gtk.MessageDialog(transient_for=win,flags=0,message_type=Gtk.MessageType.ERROR,buttons=Gtk.ButtonsType.OK,text='OptiMouse could not apply settings')
                dialog.format_secondary_text(message)
                dialog.run()
                dialog.destroy()
            return False
        def worker():
            try:
                write_settings(new)
                theme=apply(new)
                GLib.idle_add(complete,'Hyprland accepted '+theme+' at '+str(new['size'])+' px. Existing application cursors may require restart.',True)
            except Exception as exc:
                GLib.idle_add(complete,str(exc),False)
        threading.Thread(target=worker,daemon=True).start()
    def reset_click(*_):
        size.set_value(DEFAULT['size']); follow.set_active(True);shake.set_active(False)
        rgba.parse(DEFAULT['color']);chooser.set_rgba(rgba)
        set_status('Defaults selected. Press Apply settings to save.')
    apply_btn.connect('clicked',apply_click);reset.connect('clicked',reset_click)
    win.show_all();Gtk.main()

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--diagnose':
        for cmd in (['hyprctl','version'],['hyprctl','-j','cursorpos'],['systemctl','--user','status','optimouse-shake.service']):
            try:
                result=run(cmd)
                print(' '.join(cmd), 'exit', result.returncode, result.stdout[:600], result.stderr[:300])
            except Exception as exc: print(str(exc))
    elif len(sys.argv)>1 and sys.argv[1]=='--shake-daemon': daemon()
    elif len(sys.argv)>1 and sys.argv[1]=='--apply': apply(read_settings())
    else: gui()
