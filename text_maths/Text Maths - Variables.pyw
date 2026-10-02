"""
Text Maths - Variables

Units plus variables. "name = value" lines are remembered and print
nothing. Lines ending in "=" get their answer.

    L = 6m
    w = 10kN/m
    M = w*L^2/8 =        ->  M = w*L^2/8 = 45kNm
    L*2 = mm             ->  L*2 = 12000mm

The engine is text_maths_core.py, which must sit in the same folder.
"""
import text_maths_core

text_maths_core.run("variables")
