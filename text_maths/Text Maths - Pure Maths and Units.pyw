"""
Text Maths - Pure Maths and Units

Numbers with units, no variables. Answers follow the units you typed in,
and "= unit" at the end asks for that unit.

    5mm+5mm=             ->  5mm+5mm= 10mm
    20kN/m*(6m)^2/8=     ->  20kN/m*(6m)^2/8= 90kNm
    5MPa*100mm^2 = kN    ->  5MPa*100mm^2 = 0.5kN
    5kN+2m=              ->  5kN+2m= [Error: can't add a force and a length]

The engine is text_maths_core.py, which must sit in the same folder.
"""
import text_maths_core

text_maths_core.run("units")
