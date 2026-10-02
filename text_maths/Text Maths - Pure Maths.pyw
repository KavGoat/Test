"""
Text Maths - Pure Maths

Plain numbers only: no units, no variables. Every line that ends in "="
gets its answer. Angles are in degrees.

    5+5=                 ->  5+5= 10
    2^10/3=              ->  2^10/3= 341.333
    sin(30)=             ->  sin(30)= 0.5
    area = 5*3 =         ->  area = 5*3 = 15   (a label is allowed)

Run it again after editing and old answers are recalculated.

The engine is text_maths_core.py, which must sit in the same folder.
"""
import text_maths_core

text_maths_core.run("pure")
