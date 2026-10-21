"""
KeyFall - Settings Screen
Clean two-column layout, all positions % of screen size.
"""

import os
import pygame
from typing import Optional
from game.constants import *

VERSION = "v21f"


# ── Widgets ───────────────────────────────────────────────────────

class Slider:
    H = 32
    def __init__(self, x, y, w, label, lo, hi, val, color):
        self.x=x; self.y=y; self.w=w; self.label=label
        self.lo=lo; self.hi=hi; self.value=val; self.color=color
        self.dragging=False; self.hovered=False
        self.track = pygame.Rect(x, y+18, w, 6)

    @property
    def frac(self): return (self.value-self.lo)/(self.hi-self.lo)
    @property
    def handle_x(self): return int(self.track.x + self.frac*self.track.w)
    def handle_rect(self): return pygame.Rect(self.handle_x-8, self.track.centery-9, 16, 18)

    def on_mouse_down(self, pos):
        if self.handle_rect().collidepoint(pos) or self.track.collidepoint(pos):
            self.dragging=True; self._set(pos); return True
        return False
    def on_mouse_up(self): self.dragging=False
    def on_mouse_move(self, pos):
        self.hovered = pygame.Rect(self.x,self.y,self.w,self.H).collidepoint(pos)
        if self.dragging: self._set(pos)
    def _set(self, pos):
        f = max(0.0,min(1.0,(pos[0]-self.track.x)/self.track.w))
        self.value = self.lo + f*(self.hi-self.lo)

    def draw(self, surf, fn_small, fn_tiny):
        # Label + value
        surf.blit(fn_tiny.render(self.label, True, WHITE if self.hovered else GRAY),
                  (self.x, self.y))
        surf.blit(fn_tiny.render(f"{int(self.value*100)}%", True, self.color),
                  (self.x+self.w+6, self.track.y-1))
        # Track
        pygame.draw.rect(surf,(18,18,36),self.track,border_radius=3)
        fw=int(self.frac*self.track.w)
        if fw>0:
            pygame.draw.rect(surf,self.color,
                pygame.Rect(self.track.x,self.track.y,fw,self.track.h),border_radius=3)
        pygame.draw.rect(surf,GRAY,self.track,1,border_radius=3)
        # Handle
        hr=self.handle_rect()
        pygame.draw.rect(surf,WHITE if (self.dragging or self.hovered) else self.color,
                         hr,border_radius=3)


class Toggle:
    H = 28
    def __init__(self, x, y, w, label, val, color):
        self.rect=pygame.Rect(x,y,w,self.H)
        self.label=label; self.value=val; self.color=color; self.hovered=False
    def on_mouse_down(self, pos):
        if self.rect.collidepoint(pos): self.value=not self.value; return True
        return False
    def on_mouse_move(self, pos): self.hovered=self.rect.collidepoint(pos)
    def draw(self, surf, fn):
        c = self.color if self.value else GRAY
        pygame.draw.rect(surf,tuple(v//5 for v in c),self.rect,border_radius=5)
        pygame.draw.rect(surf,c,self.rect,1,border_radius=5)
        surf.blit(fn.render(f"{self.label}: {'ON' if self.value else 'OFF'}", True,
                            c),(self.rect.x+8,self.rect.y+(self.H-fn.size('A')[1])//2))


class SelectBox:
    H = 36
    MAX_INLINE = 1
    ROWS = 8

    def __init__(self, x, y, w, label, options, idx, color):
        self.x=x; self.y=y; self.w=w; self.label=label
        self.options=options; self.selected=idx; self.color=color
        self.hovered=False; self._open=False; self._scroll=0
        self.rect=pygame.Rect(x,y,w,self.H)
        bw=28
        self.lb=pygame.Rect(x,y,bw,self.H)
        self.rb=pygame.Rect(x+w-bw,y,bw,self.H)

    @property
    def value(self): return self.options[self.selected]

    def _dropdown(self): return len(self.options)>self.MAX_INLINE

    def on_mouse_down(self, pos):
        if self._dropdown():
            if self._open:
                rh=26
                for i in range(self.ROWS):
                    idx=self._scroll+i
                    if idx>=len(self.options): break
                    r=pygame.Rect(self.x,self.y+self.H+i*rh,self.w,rh)
                    if r.collidepoint(pos):
                        self.selected=idx; self._open=False; return True
                self._open=False; return False
            else:
                if self.rect.collidepoint(pos):
                    self._open=True
                    self._scroll=max(0,self.selected-self.ROWS//2)
                    return True
        else:
            if self.lb.collidepoint(pos):
                self.selected=(self.selected-1)%len(self.options); return True
            if self.rb.collidepoint(pos):
                self.selected=(self.selected+1)%len(self.options); return True
        return False

    def on_mouse_scroll(self, dy):
        if self._open:
            self._scroll=max(0,min(len(self.options)-1,self._scroll-dy))

    def on_mouse_move(self, pos): self.hovered=self.rect.collidepoint(pos)

    def draw(self, surf, fn_s, fn_t):
        surf.blit(fn_t.render(self.label,True,GRAY),(self.x,self.y-15))
        bc=self.color if (self.hovered or self._open) else GRAY
        pygame.draw.rect(surf,(12,12,24),self.rect,border_radius=5)
        pygame.draw.rect(surf,bc,self.rect,1,border_radius=5)

        if self._dropdown():
            vs=fn_s.render(str(self.value)[:40],True,WHITE)
            surf.blit(vs,(self.x+8,self.y+(self.H-vs.get_height())//2))
            ax=self.x+self.w-16; ay=self.y+self.H//2
            if self._open:
                pygame.draw.polygon(surf,self.color,[(ax-6,ay+3),(ax+6,ay+3),(ax,ay-4)])
            else:
                pygame.draw.polygon(surf,self.color,[(ax-6,ay-3),(ax+6,ay-3),(ax,ay+4)])
            if self._open:
                rh=26; dh=self.ROWS*rh
                dr=pygame.Rect(self.x,self.y+self.H,self.w,dh)
                bg=pygame.Surface((dr.w,dr.h),pygame.SRCALPHA); bg.fill((8,8,20,235))
                surf.blit(bg,(dr.x,dr.y))
                pygame.draw.rect(surf,self.color,dr,1,border_radius=3)
                for i in range(self.ROWS):
                    idx=self._scroll+i
                    if idx>=len(self.options): break
                    ry=dr.y+i*rh; rr=pygame.Rect(dr.x+1,ry,dr.w-2,rh-1)
                    if idx==self.selected:
                        hbg=pygame.Surface((rr.w,rr.h),pygame.SRCALPHA)
                        hbg.fill((*self.color,55)); surf.blit(hbg,(rr.x,rr.y))
                    tc=self.color if idx==self.selected else (150,150,170)
                    t=fn_t.render(str(self.options[idx])[:52],True,tc)
                    surf.blit(t,(rr.x+6,rr.y+(rh-t.get_height())//2))
                if len(self.options)>self.ROWS:
                    sbh=max(16,int(dh*self.ROWS/len(self.options)))
                    sby=dr.y+int((dh-sbh)*self._scroll/max(1,len(self.options)-self.ROWS))
                    pygame.draw.rect(surf,self.color,(dr.right-5,sby,3,sbh),border_radius=2)
        else:
            pygame.draw.polygon(surf,self.color,
                [(self.lb.x+20,self.lb.centery),(self.lb.x+8,self.lb.centery-7),
                 (self.lb.x+8,self.lb.centery+7)])
            pygame.draw.polygon(surf,self.color,
                [(self.rb.x+8,self.rb.centery),(self.rb.x+20,self.rb.centery-7),
                 (self.rb.x+20,self.rb.centery+7)])
            vs=fn_s.render(str(self.value),True,WHITE)
            surf.blit(vs,(self.rect.centerx-vs.get_width()//2,
                         self.rect.centery-vs.get_height()//2))


class Button:
    def __init__(self, x, y, w, h, label, color):
        self.rect=pygame.Rect(x,y,w,h)
        self.label=label; self.color=color; self.hovered=False
    def on_mouse_down(self, pos): return self.rect.collidepoint(pos)
    def on_mouse_move(self, pos): self.hovered=self.rect.collidepoint(pos)
    def draw(self, surf, fn):
        c=self.color if self.hovered else GRAY
        pygame.draw.rect(surf,tuple(v//5 for v in self.color),self.rect,border_radius=6)
        pygame.draw.rect(surf,c,self.rect,2,border_radius=6)
        t=fn.render(self.label,True,WHITE if self.hovered else GRAY)
        surf.blit(t,(self.rect.centerx-t.get_width()//2,
                     self.rect.centery-t.get_height()//2))


# ── Settings Screen ───────────────────────────────────────────────

class SettingsScreen:
    def __init__(self, screen, audio_manager, save_data, renderer=None):
        self.screen=screen; self.audio=audio_manager; self.save_data=save_data
        self.renderer=renderer
        self._tick=0.0
        self._W=self._H=0
        self._build()

    def _build(self):
        W=self.screen.get_width(); H=self.screen.get_height()
        self._W=W; self._H=H
        s=self.save_data.get("settings",{})

        # Fonts
        self.ft=pygame.font.SysFont("consolas",max(22,int(H*.052)),bold=True)
        self.fl=pygame.font.SysFont("consolas",max(15,int(H*.032)),bold=True)
        self.fm=pygame.font.SysFont("consolas",max(12,int(H*.025)),bold=True)
        self.fs=pygame.font.SysFont("consolas",max(11,int(H*.022)))
        self.fq=pygame.font.SysFont("consolas",max(9, int(H*.017)))

        # Layout: two equal columns
        pad=int(W*.04); gap=int(W*.04)
        cw=int((W-pad*2-gap)/2)
        c1=pad; c2=pad+cw+gap

        # Row grid
        top=int(H*.17); rh=int(H*.085)

        # ── Left column: Audio ──────────────────────────────────
        self.sliders=[
            Slider(c1,top+rh*0,cw,"Master Volume",0,1,s.get("master_volume",.8),NEON_CYAN),
            Slider(c1,top+rh*1,cw,"Menu Music Volume", 0,1,s.get("music_volume",.5), NEON_PURPLE),
            Slider(c1,top+rh*2,cw,"SFX Volume",   0,1,s.get("sfx_volume",.7),   NEON_YELLOW),
            Slider(c1,top+rh*3,cw,"Note Volume",  0,1,s.get("note_volume",.9),  NEON_GREEN),
        ]
        self.sfx_tog=Toggle(c1,top+rh*4+4,int(cw*.75),"SFX",
                            s.get("sfx_enabled",True),NEON_GREEN)

        # ── Right column ────────────────────────────────────────
        modes=["soundfont","synth","midi_out"]
        mi=modes.index(s.get("note_sound_mode","soundfont")) if s.get("note_sound_mode","soundfont") in modes else 0
        ports=["(none)"]+self.audio.available_out_ports
        pi=ports.index(s.get("midi_out_port","(none)")) if s.get("midi_out_port","(none)") in ports else 0
        gms=[MODE_HARD,MODE_EASY,"TESTING"]
        gi=gms.index(s.get("default_game_mode","TESTING")) if s.get("default_game_mode","TESTING") in gms else 2
        vel_v=s.get("midi_out_velocity",100)/127.0

        r2=top
        self.mode_sel =SelectBox(c2,r2,        cw,"Note Sound Mode",  modes,mi,NEON_YELLOW)
        r2+=int(rh*1.3)
        # SF2 two-level selector: category → file
        from game.fluidsynth_engine import list_sf2_categorized
        self._sf2_cats = list_sf2_categorized()
        cat_names = list(self._sf2_cats.keys()) or ["pianos"]
        cur_sf2_entry = s.get("sf2_file", "pianos/piano.sf2")
        if "/" in cur_sf2_entry:
            cur_cat, cur_fname = cur_sf2_entry.split("/", 1)
        else:
            cur_cat = "pianos"
            cur_fname = cur_sf2_entry
        cat_i = cat_names.index(cur_cat) if cur_cat in cat_names else 0
        self.sf2_cat_sel = SelectBox(c2,r2,cw,"Soundfont Category",cat_names,cat_i,NEON_CYAN)
        r2+=int(rh*0.9)
        cur_cat_files = self._sf2_cats.get(cat_names[cat_i],[]) or ["(none)"]
        file_i = cur_cat_files.index(cur_fname) if cur_fname in cur_cat_files else 0
        self.sf2_file_sel = SelectBox(c2,r2,cw,"Soundfont File",cur_cat_files,file_i,NEON_YELLOW)
        self.sf2_file_sel.MAX_INLINE = 1  # always use dropdown mode
        self.sf2_sel = self.sf2_file_sel  # compat alias
        r2+=rh
        self.port_sel =SelectBox(c2,r2,        cw,"MIDI Output Port", ports,pi,NEON_PINK)
        r2+=rh
        self.gm_sel   =SelectBox(c2,r2,        cw,"Default Game Mode",gms,  gi,NEON_ORANGE)
        r2+=rh
        # Vanishing point
        vp_opts=["Straight (0%)","Shallow (1/3)","Default (2/3)"]
        vp_vals=[0.0, 0.33, 0.67]
        cur_vp=s.get("vanish_frac",0.67)
        # Find closest
        vpi=min(range(len(vp_vals)),key=lambda i:abs(vp_vals[i]-cur_vp))
        self._vp_vals=vp_vals
        self.vp_sel=SelectBox(c2,r2,cw,"Highway Perspective",vp_opts,vpi,NEON_CYAN)
        r2+=rh
        self.vel_sl   =Slider(   c2,r2,        cw,"MIDI Out Velocity (0=file)",0,1,vel_v,NEON_PINK)
        r2+=rh
        self.btn_test =Button(   c2,r2,        cw,int(H*.048),"◆ TEST NOTE",NEON_CYAN)
        r2+=int(H*.048)+int(H*.055)

        # Menu music selector removed — use songs/_menu_music/ folder instead

        # Save / Back
        bw=int(W*.13); bh=int(H*.062); by=H-bh-int(H*.04)
        cx=W//2; gp=int(W*.018)
        self.btn_save=Button(cx-bw-gp//2,by,bw,bh,"SAVE",NEON_GREEN)
        self.btn_back=Button(cx+gp//2,   by,bw,bh,"BACK",NEON_PINK)

        self._c1=c1;self._c2=c2;self._cw=cw
        self._all=[*self.sliders,self.sfx_tog,self.mode_sel,self.sf2_cat_sel,self.sf2_file_sel,
                   self.port_sel,self.gm_sel,self.vp_sel,self.vel_sl,self.btn_test,
                   self.btn_save,self.btn_back]
        self.music_sel=None

    def handle_event(self,event)->Optional[str]:
        if self.screen.get_width()!=self._W or self.screen.get_height()!=self._H:
            self._build()

        if event.type==pygame.MOUSEMOTION:
            for w in self._all: w.on_mouse_move(event.pos)
        elif event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            for sl in self.sliders: sl.on_mouse_down(event.pos)
            self.sfx_tog.on_mouse_down(event.pos)
            for box in(self.mode_sel,self.sf2_cat_sel,self.sf2_file_sel,self.port_sel,self.gm_sel,self.vp_sel):
                if box.on_mouse_down(event.pos):
                    self.audio.play_sfx("click")
                    # Auto-open sf2_file_sel dropdown if multiple files available
                    if box is self.sf2_file_sel and len(box.options) > 1:
                        box._open = True
            self.vel_sl.on_mouse_down(event.pos)
            if self.btn_test.on_mouse_down(event.pos):
                try: self.audio.play_note_isolated(60,90)
                except: self.audio.play_note(60,90)
            if self.btn_save.on_mouse_down(event.pos):
                self.audio.play_sfx("confirm"); self._save(); self._build(); return None
            if self.btn_back.on_mouse_down(event.pos):
                self.audio.play_sfx("back"); return "back"
        elif event.type==pygame.MOUSEBUTTONUP and event.button==1:
            for sl in self.sliders: sl.on_mouse_up()
            self.vel_sl.on_mouse_up()
        elif event.type==pygame.MOUSEWHEEL:
            # Route scroll to whichever dropdown is currently open
            for box in (self.sf2_cat_sel, self.sf2_file_sel, self.mode_sel, self.port_sel, self.gm_sel, self.vp_sel):
                if getattr(box, "_open", False):
                    box.on_mouse_scroll(event.y)
                    break
            else:
                self.music_sel.on_mouse_scroll(event.y)
        elif event.type==pygame.KEYDOWN:
            if event.key==pygame.K_ESCAPE:
                self.audio.play_sfx("back"); return "back"
            if event.key==pygame.K_RETURN:
                self.audio.play_sfx("confirm"); self._save(); self._build(); return None

        self._live()
        return None

    def _live(self):
        # Update file list when category changes
        if hasattr(self,'sf2_cat_sel') and hasattr(self,'sf2_file_sel'):
            cat = self.sf2_cat_sel.value
            files = self._sf2_cats.get(cat,[]) or ["(none)"]
            if self.sf2_file_sel.options != files:
                self.sf2_file_sel.options = files
                self.sf2_file_sel.selected = 0
                self.sf2_file_sel.MAX_INLINE = 1  # keep dropdown mode after rebuild
        self.audio.master_volume=self.sliders[0].value
        self.audio.music_volume =self.sliders[1].value
        self.audio.sfx_volume   =self.sliders[2].value
        self.audio.note_volume  =self.sliders[3].value
        self.audio.sfx_enabled  =self.sfx_tog.value
        self.audio.update_volumes()

    def _save(self):
        settings={
            "master_volume":    self.sliders[0].value,
            "music_volume":     self.sliders[1].value,
            "sfx_volume":       self.sliders[2].value,
            "note_volume":      self.sliders[3].value,
            "sfx_enabled":      self.sfx_tog.value,
            "note_sound_mode":  self.mode_sel.value,
            "midi_out_port":    self.port_sel.value,
            "default_game_mode":self.gm_sel.value,
            "midi_out_velocity":int(self.vel_sl.value*127),
"vanish_frac": self._vp_vals[self.vp_sel.selected],
            "menu_music_file":  "[Default Synth]",
            "sf2_file": (self.sf2_cat_sel.value + "/" + self.sf2_file_sel.value
                          if self.sf2_cat_sel.value != "uncategorized"
                          else self.sf2_file_sel.value),
        }
        self.save_data["settings"]=settings
        # Apply soundfont change only if file actually changed
        sf2f = settings.get("sf2_file","piano.sf2")
        import game.fluidsynth_engine as _fe
        from game.fluidsynth_engine import resolve_sf2_path
        sf2_changed = (sf2f != getattr(_fe, "_current_sf2", None))
        _fe.SF2_PATH = resolve_sf2_path(sf2f)
        _fe._current_sf2 = sf2f
        if sf2_changed:
            _fe._sample_cache.clear()
            _fe._sf2_reader = None
            self.audio._fluid_ready = False
        self.audio.apply_settings(settings)

        mf = settings.get("menu_music_file","[Default Synth]")
        self.audio.stop_menu_music(200)
        self.audio._menu_music = None

        import threading as _th, os as _os
        audio_ref = self.audio

        def _reload_music():
            import time as _t
            # Always ensure SF2 is loaded before synthesising MIDI music
            if settings.get("note_sound_mode","soundfont") == "soundfont":
                if not audio_ref._fluid_ready:
                    audio_ref.init_soundfont()  # blocking
                for _ in range(50):
                    if audio_ref._fluid_ready: break
                    _t.sleep(0.1)

            # Resolve which MIDI file to use:
            # Priority 1: explicit selection in music_sel (not [Default Synth])
            # Priority 2: _menu_music folder auto-detection
            # Priority 3: synth fallback
            midi_path = None
            if mf != "[Default Synth]":
                candidate = _os.path.join(SONGS_DIR, mf)
                if _os.path.exists(candidate):
                    midi_path = candidate
            if midi_path is None:
                # Check _menu_music folder
                mm_dir = _os.path.join(SONGS_DIR, "_menu_music")
                if _os.path.isdir(mm_dir):
                    for fname in sorted(_os.listdir(mm_dir)):
                        if fname.lower().endswith((".mid", ".midi")):
                            midi_path = _os.path.join(mm_dir, fname)
                            break

            if midi_path:
                print(f"[Audio] Reloading menu music: {_os.path.basename(midi_path)}")
                audio_ref.load_menu_music_from_midi(midi_path)
            else:
                print("[Audio] Generating menu music (synth fallback)...")
                audio_ref._current_music_file = "[Default Synth]"
                audio_ref._start_music_generation()
                for _ in range(80):
                    if audio_ref._menu_music: break
                    _t.sleep(0.1)
                audio_ref.start_menu_music()

        _th.Thread(target=_reload_music, daemon=True).start()
        # Apply vanish_frac to renderer immediately if available
        if self.renderer:
            self.renderer._vanish_frac = settings.get("vanish_frac", 0.67)
        from game.save_system import save_game
        save_game(self.save_data)

    def update(self,dt): self._tick+=dt

    def draw(self):
        W,H=self._W,self._H
        import math
        self.screen.fill(DARK_BG)
        for i in range(8):
            off=(self._tick*18+i*110)%H
            pygame.draw.line(self.screen,(0,14,12),(0,int(off)),(W,int(off)),1)

        # Title
        t=self.ft.render("SETTINGS",True,NEON_CYAN)
        self.screen.blit(t,(W//2-t.get_width()//2,int(H*.03)))

        # Column headers
        h1=self.fm.render("── AUDIO ──",True,NEON_CYAN)
        h2=self.fm.render("── CONTROLS ──",True,NEON_YELLOW)
        self.screen.blit(h1,(self._c1,int(H*.12)))
        self.screen.blit(h2,(self._c2,int(H*.12)))

        for sl in self.sliders: sl.draw(self.screen,self.fs,self.fq)
        self.sfx_tog.draw(self.screen,self.fs)

        # Draw all select boxes closed first, then open dropdowns on top
        _all_sel = [b for b in [self.mode_sel,
            getattr(self,"sf2_cat_sel",None), getattr(self,"sf2_file_sel",None),
            self.port_sel, self.gm_sel, getattr(self,"vp_sel",None)] if b]
        _open_sel = [b for b in _all_sel if getattr(b, "_open", False)]
        _closed_sel = [b for b in _all_sel if not getattr(b, "_open", False)]

        for box in _closed_sel:
            box.draw(self.screen, self.fs, self.fq)

        # Soundfont status
        if self.mode_sel.value=="soundfont":
            try: st=self.audio.soundfont_status()
            except: st="unavailable"
            sc=NEON_GREEN if st=="Ready" else NEON_ORANGE
            ss=self.fq.render(f"  ● {st}",True,sc)
            self.screen.blit(ss,(self._c2,self.mode_sel.rect.bottom+2))

        self.vel_sl.draw(self.screen,self.fs,self.fq)

        # Velocity value hint
        vi=int(self.vel_sl.value*127)
        vh=self.fq.render("use file velocity" if vi==0 else f"→ sends {vi}",True,GRAY)
        self.screen.blit(vh,(self._c2,self.vel_sl.track.bottom+2))

        self.btn_test.draw(self.screen,self.fs)

        # Menu music selector removed

        # Divider
        dx=self._c1+self._cw+(self._c2-self._c1-self._cw)//2
        pygame.draw.line(self.screen,(28,28,52),(dx,int(H*.11)),(dx,H-int(H*.11)),1)

        self.btn_save.draw(self.screen,self.fl)
        self.btn_back.draw(self.screen,self.fl)

        # Open dropdowns drawn LAST — after buttons — so nothing covers them
        for box in _open_sel:
            box.draw(self.screen, self.fs, self.fq)

        hint=self.fq.render("Drag sliders · SAVE to apply · ESC = back without saving",
                            True,(38,38,55))
        self.screen.blit(hint,(W//2-hint.get_width()//2,H-int(H*.02)))

        # Music loading indicator — bottom left (same as main menu)
        status = getattr(self.audio, "music_loading_status", "")
        if status:
            import math as _m
            pulse = int(140 + 115 * abs(_m.sin(self._tick * 2.8)))
            sc = (0, pulse, 255)
            spinner = "◐◓◑◒"[int(self._tick * 4) % 4]
            ss = self.fq.render(f"{spinner} {status}", True, sc)
            self.screen.blit(ss, (16, H - int(H*.055)))
