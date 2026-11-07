"""Desktop control client (Phase 9P-h).

A thin read-only-first tkinter/ttk control & monitoring terminal
over the Control & Monitoring API. The client NEVER imports engine
internals -- it talks HTTP only, so the dependency direction is
strictly CLIENT -> CONTROL API -> QUANTENGINE.

Launch:  python -m core.client.app
         python -m core.client   (same)
"""
