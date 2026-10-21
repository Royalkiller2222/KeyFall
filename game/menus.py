"""
KeyFall - Menus v9
Song select with difficulty picker, results with PB comparison.
"""

import os, math
import pygame
from typing import Optional, List as TList
from game.constants import *
from game.midi_handler import SongData
from game.song_library import SongEntry, DIFFICULTY_ORDER, DIFFICULTY_COLORS


class MenuBase:
    def __init__(self, screen):
        self.screen = screen
        self.W = screen.get_width(); self.H = screen.get_height()
        self.fn_title = pygame.font.SysFont("consolas", 68, bold=True)
        self.fn_large = pygame.font.SysFont("consolas", 40, bold=True)
        self.fn_med   = pygame.font.SysFont("consolas", 26, bold=True)
        self.fn_small = pygame.font.SysFont("consolas", 19)
        self.fn_tiny  = pygame.font.SysFont("consolas", 14)
        self._tick = 0.0

    def update(self, dt): self._tick += dt

    def draw_centered(self, text, font, color, y, shadow=True):
        if shadow:
            s = font.render(text, True, (0,0,0))
            self.screen.blit(s,(self.W//2-s.get_width()//2+2,y+2))
        s = font.render(text, True, color)
        self.screen.blit(s,(self.W//2-s.get_width()//2,y))
        return s.get_height()

    def draw_bg(self):
        self.screen.fill(DARK_BG)
        for yy in range(0,self.H,4):
            pygame.draw.line(self.screen,(0,0,0),(0,yy),(self.W,yy),1)

    def neon_box(self, rect, color, border=2, alpha=55):
        s=pygame.Surface((rect[2],rect[3]),pygame.SRCALPHA)
        s.fill((*color,alpha)); self.screen.blit(s,(rect[0],rect[1]))
        pygame.draw.rect(self.screen,color,rect,border,border_radius=7)

    def _animated_grid(self):
        for i in range(12):
            off=(self._tick*28+i*90)%self.H
            a=int(18+8*math.sin(self._tick+i))
            pygame.draw.line(self.screen,(0,a,a//2),(0,int(off)),(self.W,int(off)),1)


# ── Main Menu ─────────────────────────────────────────────────────
class MainMenu(MenuBase):
    def __init__(self, screen, midi_ports, level, total_xp, level_progress, audio=None):
        super().__init__(screen)
        self.midi_ports=midi_ports; self.level=level
        self.total_xp=total_xp; self.level_progress=level_progress
        self.selected=0; self.options=["PLAY","FREE PLAY","SETTINGS","QUIT"]
        self.audio=audio

    def _btn_rect(self,i):
        bw,bh=340,58
        total=len(self.options)*76-18
        start_y=self.H//2-total//2+int(self.H*0.06)
        by=start_y+i*76
        return pygame.Rect(self.W//2-bw//2,by,bw,bh)

    def handle_event(self,event)->Optional[str]:
        if event.type==pygame.KEYDOWN:
            if event.key in(pygame.K_UP,pygame.K_w):
                self.selected=(self.selected-1)%len(self.options)
            elif event.key in(pygame.K_DOWN,pygame.K_s):
                self.selected=(self.selected+1)%len(self.options)
            elif event.key in(pygame.K_RETURN,pygame.K_SPACE):
                return self.options[self.selected].lower()
        elif event.type==pygame.MOUSEMOTION:
            for i in range(len(self.options)):
                if self._btn_rect(i).collidepoint(event.pos): self.selected=i
        elif event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            for i in range(len(self.options)):
                if self._btn_rect(i).collidepoint(event.pos):
                    self.selected=i; return self.options[i].lower()
        return None

    def draw(self):
        self.draw_bg(); self._animated_grid()
        t = self._tick

        # ── KEYFALL title — large pulsing cyan with letter-spacing effect ──
        title_y = int(self.H * 0.08)
        title_font = pygame.font.SysFont("consolas", max(72, int(self.H*0.13)), bold=True)
        letters = "KEYFALL"
        total_w = sum(title_font.size(ch)[0] for ch in letters) + len(letters)*4
        x = self.W//2 - total_w//2
        for i, ch in enumerate(letters):
            phase = t*2.2 + i*0.45
            r_ = int(0)
            g_ = int(200 + 55*math.sin(phase))
            b_ = int(220 + 35*math.sin(phase+1.2))
            # Shadow
            sh = title_font.render(ch, True, (0,30,40))
            self.screen.blit(sh, (x+3, title_y+3))
            # Letter
            surf = title_font.render(ch, True, (r_,g_,b_))
            self.screen.blit(surf, (x, title_y))
            x += surf.get_width() + 4

        # ── Subtitle — spaced letters with pink/purple gradient ──
        sub_y = title_y + title_font.get_height() + 4
        sub_font = pygame.font.SysFont("consolas", max(16, int(self.H*0.030)), bold=True)
        subtitle = "MIDI  KEYBOARD  LEARNING  GAME"
        # Draw a neon underline bar behind it
        sw = sub_font.size(subtitle)[0]
        bar_x = self.W//2 - sw//2 - 12
        bar_surf = pygame.Surface((sw+24, sub_font.get_height()+8), pygame.SRCALPHA)
        bar_surf.fill((255,0,180,18))
        self.screen.blit(bar_surf, (bar_x, sub_y-2))
        # Draw each word in alternating colors
        words = subtitle.split("  ")
        colors = [NEON_PINK, (200,80,255), NEON_PINK, (200,80,255)]
        # Render full string centered but tinted
        sx = self.W//2 - sw//2
        for wi, word in enumerate(words):
            wc = colors[wi % len(colors)]
            ws = sub_font.render(word, True, wc)
            # Subtle shadow
            wsh = sub_font.render(word, True, (40,0,40))
            self.screen.blit(wsh, (sx+2, sub_y+2))
            self.screen.blit(ws,  (sx,   sub_y))
            sx += ws.get_width() + sub_font.size("  ")[0]

        # ── MIDI status ──
        pt=f"MIDI: {self.midi_ports[0][:28] if self.midi_ports else 'No device'}"
        pc=NEON_GREEN if self.midi_ports else NEON_RED
        ps=self.fn_tiny.render(pt,True,pc)
        self.screen.blit(ps,(self.W-ps.get_width()-20,24))

        # ── Menu buttons ──
        for i,opt in enumerate(self.options):
            r=self._btn_rect(i); sel=(i==self.selected)
            pulse=abs(math.sin(t*3))*18
            col=NEON_CYAN if sel else GRAY
            self.neon_box((r.x,r.y,r.w,r.h),col,2,int((30+pulse) if sel else 8))
            prefix="►  " if sel else "   "
            lbl=self.fn_large.render(prefix+opt,True,WHITE if sel else GRAY)
            self.screen.blit(lbl,(r.x+20,r.y+(r.h-lbl.get_height())//2))
        self.draw_centered("↑↓ / Mouse  ·  ENTER  ·  F11 Fullscreen",self.fn_tiny,GRAY,self.H-28)

        # Music loading indicator — bottom left
        if self.audio:
            status = self.audio.music_loading_status
            if status:
                pulse = int(140 + 115 * abs(math.sin(self._tick * 2.8)))
                sc = (0, pulse, 255)
                spinner = "◐◓◑◒"[int(self._tick * 4) % 4]
                ss = self.fn_tiny.render(f"{spinner} {status}", True, sc)
                self.screen.blit(ss, (16, self.H - 46))


# ── Song Select with difficulty picker ────────────────────────────
class SongSelectMenu(MenuBase):
    def __init__(self, screen, entries: TList[SongEntry], current_mode: str,
                 midi_connected: bool, audio=None):
        super().__init__(screen)
        self.entries      = entries
        self.selected     = 0
        self.mode         = current_mode
        self.midi_connected = midi_connected
        self.audio        = audio
        self.VISIBLE      = 7
        self.LIST_Y       = 120
        self.ITEM_H       = 62
        # Per-entry selected difficulty
        self._diff_sel: dict = {}  # idx -> difficulty string
        # Preview state
        self._prev_idx    = -1
        self._prev_timer  = 0.0
        self._prev_note_i = 0
        self._prev_diff   = None  # track difficulty changes
        self._speeds=[1.0,0.75,0.5,0.25]
        self._speed_labels=["100%","75%","50%","25%"]
        self._speed_idx=0
        self._prev_t      = 0.0
        self.PREVIEW_DELAY = 0.5
        self.scroll_offset = 0
        self._anim_scales    = {}
        self._anim_vels     = {}
        self._anim_tick     = 0.0
        self._prev_selected = -1
        self._anim_selected = 0   # only changes on deliberate user input
        self._cover_cache   = {}  # idx → pygame.Surface or None
        self._refresh_cb    = None  # set by app to reload songs
        self._notif         = ""    # notification text
        self._notif_timer   = 0.0

    def _entry_diff(self, idx: int) -> str:
        entry = self.entries[idx]
        if idx not in self._diff_sel:
            # Default to easiest available
            avail = entry.available_difficulties
            for pref in ["EASY", "MEDIUM", "HARD", "EXTREME"]:
                if pref in avail:
                    self._diff_sel[idx] = pref
                    break
            else:
                self._diff_sel[idx] = avail[0] if avail else "easy"
        return self._diff_sel[idx]

    def _item_rect(self, screen_i):
        y=self.LIST_Y+screen_i*self.ITEM_H
        return pygame.Rect(38,y-3,self.W-300,self.ITEM_H-3)

    def _diff_btns(self, screen_i, entry: SongEntry):
        """Returns (rect, difficulty) for all 4 difficulty slots."""
        from game.song_library import DIFFICULTY_ORDER
        y = self.LIST_Y + screen_i * self.ITEM_H
        bw=62; bh=22; gap=4
        total_w = len(DIFFICULTY_ORDER)*(bw+gap)-gap
        bx = self.W - total_w - 18
        btns = []
        for j, d in enumerate(DIFFICULTY_ORDER):
            r = pygame.Rect(bx + j*(bw+gap), y+18, bw, bh)
            btns.append((r, d, d in entry.available_difficulties))
        return btns

    def _mode_rect(self):
        return pygame.Rect(self.W-290,22,268,40)

    def _speed_btn_rects(self):
        bw=52; bh=22; gap=6
        total=(bw+gap)*4-gap
        x0=self.W//2-total//2+40; y=self.H-50
        return [pygame.Rect(x0+i*(bw+gap),y,bw,bh) for i in range(4)]

    def _row_rect(self, screen_i):
        SEL_H=96; NORM_H=56
        row_y=self.LIST_Y
        for j in range(screen_i):
            pidx=self.scroll_offset+j
            row_y+=(SEL_H if pidx==self.selected else NORM_H)+4
        idx=self.scroll_offset+screen_i
        row_h=SEL_H if idx==self.selected else NORM_H
        return pygame.Rect(28,row_y,self.W-28,row_h)

    def handle_event(self, event)->Optional[tuple]:
        if event.type==pygame.MOUSEMOTION:
            for i in range(self.VISIBLE):
                idx=self.scroll_offset+i
                if idx>=len(self.entries): break
                if self._row_rect(i).collidepoint(event.pos):
                    pass  # hover highlight only, don't change selection on hover
        elif event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            # Open folder button
            if self._btn_open_rect().collidepoint(event.pos):
                import subprocess, os
                songs_dir=os.path.abspath("songs")
                os.makedirs(songs_dir,exist_ok=True)
                try: subprocess.Popen(f'explorer "{songs_dir}"')
                except: pass
                return None
            # Refresh button
            if self._btn_refresh_rect().collidepoint(event.pos):
                if self._refresh_cb:
                    self._refresh_cb()
                self._notif="Songs refreshed!"; self._notif_timer=2.5
                if self.audio: self.audio.play_sfx("confirm")
                return None
            # Difficulty buttons
            for i in range(self.VISIBLE):
                idx=self.scroll_offset+i
                if idx>=len(self.entries): break
                entry=self.entries[idx]
                for r,d,avail in self._diff_btns(i, entry):
                    if r.collidepoint(event.pos) and avail:
                        self._diff_sel[idx]=d
                        if self.audio: self.audio.play_sfx("click")
                        return None
            for i in range(self.VISIBLE):
                idx=self.scroll_offset+i
                if idx>=len(self.entries): break
                if self._row_rect(i).collidepoint(event.pos):
                    if self.selected==idx:
                        entry=self.entries[idx]
                        diff=self._entry_diff(idx)
                        song=entry.get_song(diff)
                        if song: return("play",song,self.mode,self._speeds[self._speed_idx])
                    else:
                        self.selected=idx
                        self._anim_selected=idx
                        if self.audio: self.audio.play_sfx("hover")
                        return None
            # Speed buttons
            for i,sr in enumerate(self._speed_btn_rects()):
                if sr.collidepoint(event.pos):
                    self._speed_idx=i
                    if self.audio: self.audio.play_sfx("click")
                    return None
            # Mode toggle
            if self._mode_rect().collidepoint(event.pos):
                modes=[MODE_HARD,MODE_EASY,MODE_TESTING]
                self.mode=modes[(modes.index(self.mode)+1)%len(modes)] \
                    if self.mode in modes else MODE_HARD
                if self.audio: self.audio.play_sfx("click")
        elif event.type==pygame.MOUSEWHEEL:
            self.scroll_offset=max(0,min(max(0,len(self.entries)-1),
                                         self.scroll_offset-event.y))
        if event.type==pygame.KEYDOWN:
            if event.key in(pygame.K_UP,pygame.K_w):
                self.selected=max(0,self.selected-1)
                self._anim_selected=self.selected
                if self.audio: self.audio.play_sfx("hover")
                if self.selected<self.scroll_offset: self.scroll_offset=self.selected
            elif event.key in(pygame.K_DOWN,pygame.K_s):
                self.selected=min(len(self.entries)-1,self.selected+1)
                self._anim_selected=self.selected
                if self.audio: self.audio.play_sfx("hover")
                if self.selected>=self.scroll_offset+self.VISIBLE:
                    self.scroll_offset=self.selected-self.VISIBLE+1
            elif event.key in(pygame.K_LEFT,pygame.K_a):
                entry=self.entries[self.selected]
                avail=entry.available_difficulties
                if avail:
                    cur=self._entry_diff(self.selected)
                    i=avail.index(cur) if cur in avail else 0
                    self._diff_sel[self.selected]=avail[(i-1)%len(avail)]
            elif event.key in(pygame.K_RIGHT,pygame.K_d):
                entry=self.entries[self.selected]
                avail=entry.available_difficulties
                if avail:
                    cur=self._entry_diff(self.selected)
                    i=avail.index(cur) if cur in avail else 0
                    self._diff_sel[self.selected]=avail[(i+1)%len(avail)]
            elif event.key==pygame.K_RETURN:
                if self.entries:
                    entry=self.entries[self.selected]
                    diff=self._entry_diff(self.selected)
                    song=entry.get_song(diff)
                    if song: return("play",song,self.mode,self._speeds[self._speed_idx])
            elif event.key==pygame.K_m:
                modes=[MODE_HARD,MODE_EASY,MODE_TESTING]
                self.mode=modes[(modes.index(self.mode)+1)%len(modes)] \
                    if self.mode in modes else MODE_HARD
            elif event.key==pygame.K_ESCAPE:
                return("back",None,None)
        return None

    def update(self, dt:float):
        super().update(dt)
        self._anim_tick += dt

        # Bounce kick when selection changes
        if not hasattr(self, '_prev_selected'): self._prev_selected = -1
        if self._prev_selected != self.selected:
            self._anim_vels[self.selected] = 5.0
            self._prev_selected = self.selected

        # Spring physics — no damping for selected (eternal bounce),
        # but add damping for unselected so they settle quickly
        K=12.0
        for i in range(len(self.entries)):
            is_sel = (i == self._anim_selected)
            target = 1.0 if is_sel else 0.0
            D      = 0.0 if is_sel else 8.0   # unselected damps out fast
            pos    = self._anim_scales.get(i, 0.0)
            vel    = self._anim_vels.get(i, 0.0)
            vel   += (-K*(pos-target) - D*vel) * dt
            pos   += vel * dt
            pos    = max(-0.15, min(1.45, pos))
            self._anim_scales[i] = pos
            self._anim_vels[i]   = vel

        self._prev_timer+=dt
        if self._notif_timer>0: self._notif_timer=max(0,self._notif_timer-dt)
        cur_diff = self._entry_diff(self.selected) if self.entries else None
        if self._prev_idx!=self.selected or self._prev_diff!=cur_diff:
            self._prev_idx=self.selected; self._prev_timer=0.0
            self._prev_note_i=0; self._prev_t=0.0
            self._prev_diff=cur_diff
            # Stop any lingering notes immediately
            try: self.audio._tone_cache.clear()
            except: pass
        if (self.audio and self._prev_timer>=self.PREVIEW_DELAY
                and self.entries and 0<=self.selected<len(self.entries)):
            entry=self.entries[self.selected]
            diff=self._entry_diff(self.selected)
            song=entry.get_song(diff)
            if song:
                self._prev_t+=dt
                while self._prev_note_i<len(song.notes):
                    note=song.notes[self._prev_note_i]
                    if note.time_sec<=self._prev_t:
                        orig=self.audio.note_volume
                        self.audio.note_volume=orig*0.45
                        self.audio.play_note(note.pitch,min(80,note.velocity))
                        self.audio.note_volume=orig
                        self._prev_note_i+=1
                    else: break
                # Loop: restart from beginning when song ends
                if song.notes and self._prev_t > song.notes[-1].time_sec + 1.0:
                    self._prev_note_i=0; self._prev_t=0.0

    def _btn_open_rect(self):
        return pygame.Rect(18, 22, 120, 34)

    def _btn_refresh_rect(self):
        return pygame.Rect(146, 22, 120, 34)

    def draw(self):
        self.draw_bg(); self._animated_grid()
        self.draw_centered("SELECT SONG",self.fn_large,NEON_CYAN,28)

        # Open folder button
        br=self._btn_open_rect()
        self.neon_box((br.x,br.y,br.w,br.h),NEON_CYAN,1,20)
        bt=self.fn_tiny.render("📁 OPEN FOLDER",True,NEON_CYAN)
        self.screen.blit(bt,(br.x+8,br.y+(br.h-bt.get_height())//2))

        # Refresh button
        rr=self._btn_refresh_rect()
        self.neon_box((rr.x,rr.y,rr.w,rr.h),NEON_GREEN,1,20)
        rt=self.fn_tiny.render("↻ REFRESH",True,NEON_GREEN)
        self.screen.blit(rt,(rr.x+8,rr.y+(rr.h-rt.get_height())//2))

        # Notification
        if self._notif_timer>0:
            nt=self.fn_tiny.render(self._notif,True,NEON_YELLOW)
            self.screen.blit(nt,(18,60))
        mode_c={MODE_HARD:NEON_RED,MODE_EASY:NEON_GREEN,MODE_TESTING:NEON_ORANGE}.get(self.mode,GRAY)
        mr=self._mode_rect()
        self.neon_box((mr.x,mr.y,mr.w,mr.h),mode_c,2,30)
        ms=self.fn_small.render(f"[M]  MODE: {self.mode}",True,mode_c)
        self.screen.blit(ms,(mr.x+10,mr.y+(mr.h-ms.get_height())//2))

        if not self.entries:
            self.draw_centered("No songs found — place folders or .mid files in songs/",
                               self.fn_med,NEON_RED,self.H//2-30)
            return

        SEL_H=96; NORM_H=56; DIFF_BW=74; DIFF_BH=32
        COVER=50  # cover art square size
        from game.song_library import DIFFICULTY_ORDER

        for i in range(self.VISIBLE):
            idx=self.scroll_offset+i
            if idx>=len(self.entries): break
            entry=self.entries[idx]; sel=(idx==self._anim_selected)
            scale = self._anim_scales.get(idx, 0.0)
            # Row height is FIXED — only text animates
            row_h = SEL_H if (idx == self.selected) else NORM_H

            # Row Y — based on fixed heights only
            row_y=self.LIST_Y
            for j in range(i):
                pidx=self.scroll_offset+j
                row_y+=(SEL_H if pidx==self.selected else NORM_H)+4

            r=pygame.Rect(28,row_y,self.W-28,row_h)

            if sel:
                self.neon_box((r.x,r.y,r.w,r.h),NEON_CYAN,2,22)
            else:
                pygame.draw.rect(self.screen,(12,12,22),r,border_radius=6)
                pygame.draw.rect(self.screen,(26,26,44),r,1,border_radius=6)

            # Cover art
            COVER=50
            cover_x = r.x + 8
            cover_y = row_y + (row_h - COVER)//2
            if idx not in self._cover_cache:
                img = None
                if entry.folder:
                    for ext in ['cover.png','cover.jpg','cover.jpeg','art.png','art.jpg']:
                        cp = os.path.join(entry.folder, ext)
                        if os.path.exists(cp):
                            try:
                                raw = pygame.image.load(cp).convert()
                                img = pygame.transform.smoothscale(raw,(COVER,COVER))
                            except Exception: pass
                            break
                self._cover_cache[idx] = img
            cover_img = self._cover_cache.get(idx)
            if cover_img:
                self.screen.blit(cover_img,(cover_x,cover_y))
                pygame.draw.rect(self.screen,NEON_CYAN,
                    pygame.Rect(cover_x,cover_y,COVER,COVER),1,border_radius=3)
            else:
                # Placeholder
                ph = pygame.Rect(cover_x,cover_y,COVER,COVER)
                pygame.draw.rect(self.screen,(22,22,38),ph,border_radius=3)
                pygame.draw.rect(self.screen,(45,45,65),ph,1,border_radius=3)
                pf = pygame.font.SysFont("consolas",18,bold=True)
                ps = pf.render("♪",True,(55,55,80))
                self.screen.blit(ps,(ph.centerx-ps.get_width()//2,ph.centery-ps.get_height()//2))

            text_x = cover_x + COVER + 10

            # Song name — text scales smoothly with spring value
            sc_t = max(0.0, min(1.3, scale))
            base_size = 16
            sel_size  = 33
            nf = pygame.font.SysFont("consolas", sel_size, bold=True)
            nc = WHITE if sel else (140,140,165)
            name_s = nf.render(entry.title[:38], True, nc)
            txt_scale = (base_size/sel_size) + (1.0 - base_size/sel_size) * sc_t
            if txt_scale < 0.99:
                tw = max(1, int(name_s.get_width()  * txt_scale))
                th = max(1, int(name_s.get_height() * txt_scale))
                name_s = pygame.transform.smoothscale(name_s, (tw, th))
            self.screen.blit(name_s,(text_x, row_y+(row_h-name_s.get_height())//2))

            # Song info (fades in as row expands)
            if scale>0.35:
                song=entry.get_song(self._entry_diff(idx))
                if song:
                    info=(f"{song.bpm:.0f} BPM  ·  "
                          f"{int(song.duration_sec//60)}:{int(song.duration_sec%60):02d}  ·  "
                          f"{len(song.notes)} notes")
                    alpha=int(min(255,(scale-0.35)/0.65*255))
                    inf_s=self.fn_tiny.render(info,True,NEON_PURPLE)
                    inf_surf=pygame.Surface(inf_s.get_size(),pygame.SRCALPHA)
                    inf_surf.blit(inf_s,(0,0)); inf_surf.set_alpha(alpha)
                    self.screen.blit(inf_surf,(r.x+14,row_y+row_h-inf_s.get_height()-5))

            # Difficulty buttons — right side, scaled
            cur_diff=self._entry_diff(idx)
            total_dw=len(DIFFICULTY_ORDER)*(DIFF_BW+4)-4
            dbx=self.W-total_dw-22
            for j,d in enumerate(DIFFICULTY_ORDER):
                avail=d in entry.available_difficulties
                is_cur=(d==cur_diff and avail)
                dbr=pygame.Rect(dbx+j*(DIFF_BW+4),row_y+(row_h-DIFF_BH)//2,DIFF_BW,DIFF_BH)
                dc=DIFFICULTY_COLORS.get(d,(128,128,128))
                if not avail:
                    # Unavailable: very dim, barely visible
                    pygame.draw.rect(self.screen,(14,14,22),dbr,border_radius=5)
                    pygame.draw.rect(self.screen,(28,28,40),dbr,1,border_radius=5)
                    dt=self.fn_tiny.render(d,True,(35,35,50))
                else:
                    # Available: bright fill + strong border
                    bg_a=90 if is_cur else 45
                    bg=pygame.Surface((dbr.w,dbr.h),pygame.SRCALPHA)
                    bg.fill((*dc,bg_a)); self.screen.blit(bg,(dbr.x,dbr.y))
                    border_col = dc if is_cur else tuple(min(255,int(c*0.75)) for c in dc)
                    pygame.draw.rect(self.screen,border_col,
                                     dbr,2,border_radius=5)
                    if is_cur:
                        # Extra glow ring for selected difficulty
                        glow=pygame.Surface((dbr.w+6,dbr.h+6),pygame.SRCALPHA)
                        pygame.draw.rect(glow,(*dc,60),(0,0,dbr.w+6,dbr.h+6),2,border_radius=7)
                        self.screen.blit(glow,(dbr.x-3,dbr.y-3))
                    df=pygame.font.SysFont("consolas",max(11,int(10+4*scale)),bold=is_cur)
                    dt=df.render(d,True,WHITE if is_cur else dc)
                self.screen.blit(dt,(dbr.centerx-dt.get_width()//2,
                                     dbr.centery-dt.get_height()//2))

        if len(self.entries)>self.VISIBLE:
            total=len(self.entries)
            sb_h=max(20,int(self.H*0.6*self.VISIBLE/total))
            sb_y=self.LIST_Y+int(self.H*0.6*self.scroll_offset/total)
            pygame.draw.rect(self.screen,GRAY,(self.W-8,sb_y,4,sb_h),border_radius=2)

        for i,sr in enumerate(self._speed_btn_rects()):
            is_sel=(i==self._speed_idx)
            col=NEON_CYAN if is_sel else GRAY
            pygame.draw.rect(self.screen,(0,30,40) if is_sel else (10,10,20),sr,border_radius=5)
            pygame.draw.rect(self.screen,col,sr,2 if is_sel else 1,border_radius=5)
            lbl=self.fn_tiny.render(self._speed_labels[i],True,col)
            self.screen.blit(lbl,(sr.centerx-lbl.get_width()//2,sr.centery-lbl.get_height()//2))
        sl=self.fn_tiny.render("SPEED:",True,GRAY)
        self.screen.blit(sl,(self._speed_btn_rects()[0].x-sl.get_width()-8,self.H-50+3))

        midi_c=NEON_GREEN if self.midi_connected else NEON_ORANGE
        ms2=self.fn_tiny.render(
            "● MIDI Connected" if self.midi_connected else "● MIDI Not Connected",
            True,midi_c)
        self.screen.blit(ms2,(18,self.H-46))
        self.draw_centered(
            "↑↓: Navigate  ·  ENTER: Play  ·  ←→: Difficulty  ·  M: Mode  ·  ESC: Back",
            self.fn_tiny,GRAY,self.H-24)

# ── Results Screen ────────────────────────────────────────────────
class ResultsScreen(MenuBase):
    def __init__(self, screen, stats, song_title:str, xp_system, personal_best:Optional[dict]):
        super().__init__(screen)
        self.stats=stats; self.song_title=song_title
        self.xp_system=xp_system; self.pb=personal_best
        self.grade=stats.get_grade(); self._show_timer=0.0; self.selected=0
        self._btns=["RETRY","MAIN MENU"]

    def _btn_rect(self,i):
        bw=220; total=len(self._btns)*bw+(len(self._btns)-1)*24
        sx=self.W//2-total//2
        return pygame.Rect(sx+i*(bw+24),self.H-80,bw,50)

    def handle_event(self,event)->Optional[str]:
        if event.type==pygame.MOUSEMOTION:
            for i in range(len(self._btns)):
                if self._btn_rect(i).collidepoint(event.pos): self.selected=i
        elif event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            for i in range(len(self._btns)):
                if self._btn_rect(i).collidepoint(event.pos):
                    return["retry","menu"][i]
        if event.type==pygame.KEYDOWN:
            if event.key in(pygame.K_LEFT,pygame.K_a):
                self.selected=(self.selected-1)%len(self._btns)
            elif event.key in(pygame.K_RIGHT,pygame.K_d):
                self.selected=(self.selected+1)%len(self._btns)
            elif event.key==pygame.K_RETURN:
                return["retry","menu"][self.selected]
            elif event.key==pygame.K_ESCAPE:
                return"menu"
        return None

    def update(self,dt): super().update(dt); self._show_timer+=dt

    def _delta(self,cur,pb_val,higher=True,fmt="{:.0f}"):
        if pb_val is None: return""
        diff=cur-pb_val
        if abs(diff)<0.01: return"  =  PB"
        if(diff>0)==higher:
            return f"  ▲ +{fmt.format(abs(diff))}{'  NEW PB!' if diff>0 else ''}"
        return f"  ▼ -{fmt.format(abs(diff))}"

    def draw(self):
        self.draw_bg(); self._animated_grid()
        self.draw_centered("RESULTS",self.fn_large,NEON_CYAN,18)
        self.draw_centered(self.song_title[:50],self.fn_small,WHITE,62)
        gc={"GODLIKE":(255,220,0),"SS":NEON_CYAN,"S":(0,200,255),
            "A":NEON_GREEN,"B":NEON_YELLOW,"C":NEON_ORANGE,"F":NEON_RED}.get(self.grade,WHITE)
        pulse=1.0+0.06*math.sin(self._tick*3)
        gsz=72 if self.grade=="GODLIKE" else 108
        gf=pygame.font.SysFont("consolas",int(gsz*pulse),bold=True)
        self.draw_centered(self.grade,gf,gc,88)
        col_w=self.W//2-20
        rows=[
            ("SCORE",f"{self.stats.score:,}",NEON_CYAN,
             self._delta(self.stats.score,self.pb.get("score") if self.pb else None,True,"{:.0f}")),
            ("ACCURACY",f"{self.stats.accuracy:.1f}%",NEON_GREEN,
             self._delta(self.stats.accuracy,self.pb.get("accuracy") if self.pb else None,True,"{:.1f}")),
            ("MAX COMBO",f"x{self.stats.max_combo}",NEON_YELLOW,
             self._delta(self.stats.max_combo,self.pb.get("combo") if self.pb else None,True,"{:.0f}")),
            ("MAX STREAK",f"{self.stats.max_streak}",NEON_ORANGE,
             self._delta(self.stats.max_streak,self.pb.get("streak") if self.pb else None,True,"{:.0f}")),
        ]
        for ri,(label,val,col,delta) in enumerate(rows):
            show=min(1.0,(self._show_timer-ri*0.09)*4.0)
            if show<=0: continue
            ry=230+ri*68; rx=20
            self.neon_box((rx,ry,col_w,58),col,1,int(18*show))
            self.screen.blit(self.fn_tiny.render(label,True,GRAY),(rx+12,ry+6))
            self.screen.blit(self.fn_med.render(val,True,col),(rx+12,ry+24))
            if delta:
                dc=NEON_GREEN if "NEW PB" in delta else(NEON_CYAN if "▲" in delta else(NEON_YELLOW if"="in delta else NEON_RED))
                ds=self.fn_tiny.render(delta,True,dc)
                self.screen.blit(ds,(rx+col_w-ds.get_width()-10,ry+30))
        bx=self.W//2+10; bw2=self.W//2-30
        self.screen.blit(self.fn_small.render("HIT BREAKDOWN",True,GRAY),(bx,228))
        breakdown=[("PERFECT",self.stats.hits_perfect,NEON_CYAN),
                   ("GREAT",self.stats.hits_great,NEON_GREEN),
                   ("GOOD",self.stats.hits_good,NEON_YELLOW),
                   ("MISS",self.stats.misses,NEON_RED)]
        total_n=max(1,sum(v for _,v,_ in breakdown)); cy2=258
        for label,count,col in breakdown:
            show=min(1.0,(self._show_timer-0.3)*3.0)
            if show<=0: continue
            frac=count/total_n; bw_=int(bw2*frac*show)
            pygame.draw.rect(self.screen,(16,16,28),(bx,cy2,bw2,38),border_radius=5)
            if bw_>0: pygame.draw.rect(self.screen,col,(bx,cy2,bw_,38),border_radius=5)
            pygame.draw.rect(self.screen,GRAY,(bx,cy2,bw2,38),1,border_radius=5)
            self.screen.blit(self.fn_tiny.render(label,True,WHITE),(bx+8,cy2+4))
            self.screen.blit(self.fn_small.render(str(count),True,WHITE),(bx+8,cy2+18))
            pct=self.fn_tiny.render(f"{frac*100:.0f}%",True,GRAY)
            self.screen.blit(pct,(bx+bw2-pct.get_width()-8,cy2+12)); cy2+=52
        if self.pb:
            pb_y=510
            self.screen.blit(self.fn_small.render("PERSONAL BEST  (before this run)",True,GRAY),(20,pb_y))
            pb_row=(f"Score: {self.pb.get('score',0):,}   Acc: {self.pb.get('accuracy',0):.1f}%"
                    f"   Grade: {self.pb.get('grade','–')}   Combo: x{self.pb.get('combo',0)}")
            self.screen.blit(self.fn_small.render(pb_row,True,NEON_PURPLE),(20,pb_y+22))
        else:
            self.screen.blit(self.fn_small.render("First time playing this song!",True,NEON_GREEN),(20,510))
        # No XP bar — leveling system removed
        for i,(label,col) in enumerate(zip(self._btns,[NEON_GREEN,NEON_CYAN])):
            r=self._btn_rect(i); sel=(i==self.selected)
            self.neon_box((r.x,r.y,r.w,r.h),col if sel else GRAY,2,38 if sel else 10)
            ls=self.fn_small.render(label,True,WHITE if sel else GRAY)
            self.screen.blit(ls,(r.centerx-ls.get_width()//2,r.centery-ls.get_height()//2))
        self.draw_centered("← → / Mouse  ·  ENTER Select",self.fn_tiny,GRAY,self.H-20)
