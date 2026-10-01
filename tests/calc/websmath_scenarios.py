"""The same keystrokes for both apps. ("at", x, y) clicks the red cross at
SMath pixels, a string types characters, ("key", name) presses a named key,
("snap", name) records the focused equation (or the last one) as drawn."""
SCENARIOS = {
    "sum": [("at", 18, 18), "2+3=", ("snap", "typing"), ("key", "Return"), ("snap", "left")],
    "unit_def": [("at", 18, 18), "x:2'", ("snap", "apostrophe"), "kN", ("snap", "unit"),
                 ("key", "Return"), ("snap", "left")],
    "result_unit": [("at", 18, 18), "x:2'kN", ("key", "Return"), ("at", 18, 72), "x=",
                    ("snap", "result"), ("key", "Right"), ("snap", "in_unit_box"), "N",
                    ("snap", "unit_typed"), ("key", "Return"), ("snap", "left")],
    "not_defined": [("at", 18, 18), "q*2=", ("snap", "typing"), ("key", "Return"),
                    ("snap", "error")],
    "fraction": [("at", 18, 18), "1/3=", ("snap", "typing"), ("key", "Return"), ("snap", "left")],
    "power_sqrt": [("at", 18, 18), "\\2", ("key", "Right"), "+x^2", ("snap", "typing"),
                   ("key", "Return"), ("snap", "left")],
    "function": [("at", 18, 18), "f(z", ("key", "Right"), ":z^2", ("key", "Return"),
                 ("at", 18, 72), "f(3", ("key", "Right"), "=", ("snap", "typing"),
                 ("key", "Return"), ("snap", "left")],
    "units_maths": [("at", 18, 18), "M:12.5'kN*'m", ("key", "Return"), ("at", 18, 72),
                    "b:300'mm", ("key", "Return"), ("at", 18, 126), "M/b=",
                    ("snap", "typing"), ("key", "Return"), ("snap", "left")],
    "mismatch": [("at", 18, 18), "2'm+3'kg=", ("key", "Return"), ("snap", "error")],
    "autocomplete": [("at", 18, 18), "si", ("snap", "typing")],
    "back_and_edit": [("at", 18, 18), "12+34", ("key", "Left"), ("key", "Left"),
                      ("snap", "middle"), ("key", "Backspace"), ("snap", "deleted")],
    "matrix_eval": [("at", 18, 18), "a:5", ("key", "Return"), ("at", 18, 72), "a*a=",
                    ("key", "Return"), ("snap", "left")],
}

# Edit mode (2026-10-01): ("click", n, dx, dy) clicks the n-th equation made
# (0 first) at region pixels from its frame's corner.
D = [("at", 18, 18), "x:2'kN", ("key", "Return")]
R = D + [("at", 18, 72), "x=", ("key", "Return")]
EDIT_SCENARIOS = {
    "reopen_name": R + [("click", 1, 8, 12), ("snap", "a"), ("key", "Right"), ("snap", "b"),
                        ("key", "Right"), ("snap", "c"), ("key", "Right"), ("snap", "d")],
    "reopen_value": R + [("click", 1, 30, 12), ("snap", "a")],
    "reopen_unit_click": R + [("click", 1, 52, 12), ("snap", "a"), "'N", ("snap", "b"),
                              ("key", "Return"), ("snap", "c")],
    "reopen_end": R + [("click", 1, 8, 12), ("key", "End"), ("snap", "a"), ("key", "Right"),
                       ("snap", "b"), ("key", "Left"), ("snap", "c")],
    "def_edit_number": D + [("click", 0, 30, 12), ("snap", "a"), ("key", "Backspace"), "7",
                            ("snap", "b"), ("key", "Return"), ("snap", "c")],
    "def_edit_unit": D + [("click", 0, 50, 12), ("snap", "a"), ("key", "Backspace"),
                          ("snap", "b"), "M", ("snap", "c"), ("key", "Return"), ("snap", "d")],
    "home_end": [("at", 18, 18), "a+b+c", ("key", "Home"), ("snap", "home"), ("key", "End"),
                 ("snap", "end"), ("key", "Escape"), ("snap", "esc")],
    "fraction_nav": [("at", 18, 18), "1/3", ("snap", "den"), ("key", "Up"), ("snap", "up"),
                     ("key", "Down"), ("snap", "down"), ("key", "Right"), ("snap", "out"),
                     "+1=", ("snap", "done")],
    "unit_box_tab": R + [("click", 1, 8, 12), ("key", "End"), ("key", "Tab"), ("snap", "tab")],
    "delete_key": [("at", 18, 18), "12+34", ("key", "Home"), ("key", "Delete"), ("snap", "a")],
    "error_then_fix": [("at", 18, 18), "y=", ("key", "Return"), ("snap", "err"),
                       ("at", 18, 72), "y:3", ("key", "Return"), ("snap", "def")],
    "power_edit": [("at", 18, 18), "x^2", ("snap", "in_power"), ("key", "Right"), ("snap", "out"),
                   "*3=", ("key", "Return"), ("snap", "left")],
}
SCENARIOS.update(EDIT_SCENARIOS)
