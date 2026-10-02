"""
Text Maths - Variables with Substitution

Same as Text Maths - Variables, but it also shows the working with the
values put in:

    L = 6m
    w = 10kN/m
    M = w*L^2/8 =        ->  M = w*L^2/8 = 10kN/m*(6m)^2/8 = 45kNm

The engine is text_maths_core.py, which must sit in the same folder.
"""
import text_maths_core

text_maths_core.run("substitution")
