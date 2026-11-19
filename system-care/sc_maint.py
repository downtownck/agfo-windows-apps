# -*- coding: utf-8 -*-
"""AGFO System Care — Bakim ve saglik sayfasi. App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class MaintPage:
    # ------------------------------------------------------------------ BAKIM ve SAGLIK
    def _tab_maint(self, f):
        canvas = tk.Frame(f, bg=PANEL); canvas.pack(fill='both', expand=True)
        wrap = int(560 * self.scale)
        for col, (group, actions) in enumerate(ACTIONS.items()):
            colf = tk.Frame(canvas, bg=PANEL); colf.grid(row=0, column=col, sticky='nsew', padx=(16, 8), pady=10)
            canvas.grid_columnconfigure(col, weight=1)
            tk.Label(colf, text=group, fg=ACCENT, bg=PANEL, font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(0, 4))
            for title, action, detail, danger in actions:
                line = tk.Frame(colf, bg=PANEL2, padx=12, pady=9); line.pack(fill='x', pady=4)
                c = tk.Frame(line, bg=PANEL2); c.pack(side='left', fill='x', expand=True)
                tk.Label(c, text=title, fg=FG, bg=PANEL2, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
                tk.Label(c, text=detail + (' Yönetici gerekir.' if action in ADMIN_ACTIONS else ''), fg=MUTED, bg=PANEL2, font=('Segoe UI', 9),
                         wraplength=wrap, justify='left').pack(anchor='w', pady=(3, 0))
                self.btn(line, 'Çalıştır', lambda a=action, d=danger: self.run_ps(a, d), 'danger' if danger else 'normal', side='right')

    def run_ps(self, action, danger):
        if not self.need_admin(action):
            return
        if danger and not messagebox.askyesno('İşlemi onaylayın', DANGER_TEXT.get(action, action) + '\n\nDevam edilsin mi?'):
            return
        no_cancel = action in ('component-clean', 'health-repair', 'restore-point')
        title = next((t for acts in ACTIONS.values() for t, a, _, _ in acts if a == action), action)
        self.start([Job(title, cmd=ps_cmd(action), cancel_ok=not no_cancel)])


register_palette_module(globals())
