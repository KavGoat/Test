"""Autocomplete entries as SMath Cloud sends them (GET .../suggestions),
captured for every letter: name -> (origin, argument count, description).

Origin 1 is SMath's core, 2 a plugin, 3 the worksheet; the list shows
an icon for function / unit / operand by origin, and the description
(HTML) in a tooltip next to the list.  Generated - do not edit.
"""

SUGGESTION_META = {"'%": (1, 0, 'Percentage'),
 "'Angstrom": (1, 0, 'Angstrom'),
 "'B": (1, 0, 'Byte'),
 "'BTU": (1, 0, 'British thermal unit'),
 "'Bq": (1, 0, 'Becquerel'),
 "'Ci": (1, 0, 'Curie'),
 "'D": (1, 0, 'Debye'),
 "'F": (1, 0, 'Farad'),
 "'Fd": (1, 0, 'Faraday'),
 "'Fr": (1, 0, 'Franklin (Statcoulomb)'),
 "'G": (1, 0, 'Gauss'),
 "'G.N": (1, 0, 'Newtonian constant of gravitation'),
 "'GB": (1, 0, 'Gigabyte'),
 "'GBq": (1, 0, 'Gigabecquerel'),
 "'GHz": (1, 0, 'Gigahertz'),
 "'GJ": (1, 0, 'Gigajoule'),
 "'GN": (1, 0, 'Giganewton'),
 "'GPa": (1, 0, 'Gigapascal'),
 "'GW": (1, 0, 'Gigawatt'),
 "'Gbit": (1, 0, 'Gigabit'),
 "'GeV": (1, 0, 'Gigaelectronvolt'),
 "'Gi": (1, 0, 'Gilbert'),
 "'GiB": (1, 0, 'Gibibyte'),
 "'Gy": (1, 0, 'Gray'),
 "'Hz": (1, 0, 'Hertz'),
 "'J": (1, 0, 'Joule'),
 "'L": (1, 0, 'Liter'),
 "'MB": (1, 0, 'Megabyte'),
 "'MBq": (1, 0, 'Megabecquerel'),
 "'MHz": (1, 0, 'Megahertz'),
 "'MJ": (1, 0, 'Megajoule'),
 "'MN": (1, 0, 'Meganewton'),
 "'MPa": (1, 0, 'Megapascal'),
 "'MW": (1, 0, 'Megawatt'),
 "'Mbit": (1, 0, 'Megabit'),
 "'MeV": (1, 0, 'Megaelectronvolt'),
 "'Mg": (1, 0, 'Megagram'),
 "'MiB": (1, 0, 'Mebibyte'),
 "'Mohm": (1, 0, 'Megohm'),
 "'Mx": (1, 0, 'Maxwell'),
 "'MΩ": (1, 0, 'Megohm'),
 "'N": (1, 0, 'Newton'),
 "'N.A": (1, 0, "Avogadro's number"),
 "'Oe": (1, 0, 'Oersted'),
 "'P": (1, 0, 'Poise'),
 "'R": (1, 0, 'Roentgen'),
 "'R.m": (1, 0, 'Gas constant'),
 "'Smoot": (1, 0, 'Smoot'),
 "'St": (1, 0, 'Stokes'),
 "'Sv": (1, 0, 'Sievert'),
 "'TB": (1, 0, 'Terabyte'),
 "'THz": (1, 0, 'THz'),
 "'TJ": (1, 0, 'Terajoule'),
 "'TN": (1, 0, 'Teranewton'),
 "'Tbit": (1, 0, 'Terabit'),
 "'TeV": (1, 0, 'Teraelectronvolt'),
 "'TiB": (1, 0, 'Tebibyte'),
 "'V": (1, 0, 'Volt'),
 "'W": (1, 0, 'Watt'),
 "'Wb": (1, 0, 'Weber'),
 "'a": (1, 0, 'Are'),
 "'acre": (1, 0, 'Acre'),
 "'arcmin": (1, 0, 'Minute of arc'),
 "'arcsec": (1, 0, 'Second of arc'),
 "'atm": (1, 0, 'Atmosphere'),
 "'atom": (1, 0, 'Atom'),
 "'au": (1, 0, 'Astronomical unit'),
 "'bar": (1, 0, 'Bar'),
 "'barn": (1, 0, 'Barns'),
 "'bit": (1, 0, 'Bit'),
 "'bohr": (1, 0, 'Bohr'),
 "'byte": (1, 0, 'Byte'),
 "'c": (1, 0, 'Speed of light'),
 "'ca": (1, 0, 'Centiare'),
 "'cal": (1, 0, 'Calorie'),
 "'cd": (1, 0, 'Candela'),
 "'cm": (1, 0, 'Centimeter'),
 "'ct": (1, 0, 'Metric carat'),
 "'dB": (1, 0, 'Decibel'),
 "'dS": (1, 0, 'Decisiemens'),
 "'daB": (1, 0, 'Dekabel'),
 "'daa": (1, 0, 'Decare'),
 "'day": (1, 0, 'Day'),
 "'deg": (1, 0, 'Degree'),
 "'den": (1, 0, 'Denier'),
 "'dm": (1, 0, 'Decimeter'),
 "'dpi": (1, 0, 'Dots per inch'),
 "'dyn": (1, 0, 'Dyne'),
 "'dyne": (1, 0, 'Dyne'),
 "'e": (1, 0, 'Elementary charge'),
 "'eV": (1, 0, 'Electronvolt'),
 "'erg": (1, 0, 'Unit of energy and mechanical work'),
 "'farad": (1, 0, 'Farad'),
 "'faraday": (1, 0, 'Faraday'),
 "'ft": (1, 0, 'Foot'),
 "'furlong": (1, 0, 'Furlong'),
 "'g.e": (1, 0, 'Gravitational acceleration'),
 "'gal": (1, 0, 'Gallon'),
 "'gauss": (1, 0, 'Gauss'),
 "'gf": (1, 0, 'Gram-force'),
 "'gon": (1, 0, 'Grad - gon'),
 "'grad": (1, 0, 'Grad - gon'),
 "'gram": (1, 0, 'Gram'),
 "'h": (1, 0, 'Planck constant'),
 "'ha": (1, 0, 'Hectare'),
 "'henry": (1, 0, 'Henry'),
 "'hhp": (1, 0, 'Water Horsepower'),
 "'hildebrand": (1, 0, 'Hildebrand, solubility parameter'),
 "'hp": (1, 0, 'Horsepower'),
 "'hr": (1, 0, 'Hour'),
 "'in": (1, 0, 'Inch'),
 "'inHg": (1, 0, 'Inch of mercury'),
 "'joule": (1, 0, 'Joule'),
 "'k": (1, 0, 'Boltzmann constant'),
 "'kA": (1, 0, 'Kiloampere'),
 "'kB": (1, 0, 'Kilobyte'),
 "'kBq": (1, 0, 'Kilobecquerel'),
 "'kHz": (1, 0, 'Kilohertz'),
 "'kJ": (1, 0, 'Kilojoule'),
 "'kPa": (1, 0, 'Kilopascal'),
 "'kV": (1, 0, 'Kilovolt'),
 "'kW": (1, 0, 'Kilowatt'),
 "'kat": (1, 0, 'Katal'),
 "'katal": (1, 0, 'Katal'),
 "'kbit": (1, 0, 'Kilobit'),
 "'kcal": (1, 0, 'Kilocalorie'),
 "'keV": (1, 0, 'Electronvolt'),
 "'kg": (1, 0, 'Kilogram'),
 "'kgf": (1, 0, 'Kilogram Force'),
 "'kiB": (1, 0, 'Kibibyte'),
 "'kip": (1, 0, 'Kip'),
 "'klm": (1, 0, 'klm'),
 "'klx": (1, 0, 'klx'),
 "'km": (1, 0, 'Kilometer'),
 "'kmol": (1, 0, 'Kilomole'),
 "'kn": (1, 0, 'Knot'),
 "'knot": (1, 0, 'Knot'),
 "'kohm": (1, 0, 'Kilohm'),
 "'kph": (1, 0, 'Kilometers per hour'),
 "'kpsi": (1, 0, 'kpsi'),
 "'ks": (1, 0, 'Kilosecond'),
 "'ksf": (1, 0, 'Kilo-pounds-force per square foot'),
 "'ksi": (1, 0, 'Kilo-pounds-force per square inch'),
 "'kΩ": (1, 0, 'Kilohm'),
 "'lb": (1, 0, 'Pound'),
 "'lb.m": (1, 0, 'Pound'),
 "'lbf": (1, 0, 'Pound-force'),
 "'lbm": (1, 0, 'Pound'),
 "'lbmol": (1, 0, 'Pound-mole'),
 "'lm": (1, 0, 'Lumen'),
 "'lx": (1, 0, 'Lux'),
 "'ly": (1, 0, 'Light-year'),
 "'m": (1, 0, 'Meter'),
 "'m.e": (1, 0, 'Electron mass'),
 "'m.n": (1, 0, 'Neutron mass'),
 "'m.p": (1, 0, 'Proton mass'),
 "'mA": (1, 0, 'Milliampere'),
 "'mC": (1, 0, 'Millicoulomb'),
 "'mCi": (1, 0, 'Millicurie'),
 "'mF": (1, 0, 'Millifarad'),
 "'mH": (1, 0, 'Millihenry'),
 "'mL": (1, 0, 'Milliliter'),
 "'mR": (1, 0, 'Milliroentgen'),
 "'mT": (1, 0, 'mT'),
 "'mV": (1, 0, 'Millivolt'),
 "'mWb": (1, 0, 'mWb'),
 "'mi": (1, 0, 'Mile'),
 "'micron": (1, 0, 'Micrometer'),
 "'mile": (1, 0, 'Mile'),
 "'min": (1, 0, 'Minute'),
 "'mm": (1, 0, 'Millimeter'),
 "'mmHg": (1, 0, 'Torr'),
 "'mmol": (1, 0, 'Millimole'),
 "'mol": (1, 0, 'Mole'),
 "'month": (1, 0, 'Month'),
 "'mph": (1, 0, 'Miles per hour'),
 "'ms": (1, 0, 'Millisecond'),
 "'nA": (1, 0, 'Nanoampere'),
 "'nC": (1, 0, 'Nanocoulomb'),
 "'nF": (1, 0, 'Nanofarad'),
 "'nH": (1, 0, 'Nanohenry'),
 "'nJ": (1, 0, 'nJ'),
 "'nN": (1, 0, 'nN'),
 "'nV": (1, 0, 'Nanovolt'),
 "'nW": (1, 0, 'Nanowatt'),
 "'nm": (1, 0, 'Nanometer'),
 "'nmi": (1, 0, 'Nautical mile'),
 "'nmol": (1, 0, 'nmol'),
 "'ns": (1, 0, 'Nanosecond'),
 "'nt": (1, 0, 'Nit'),
 "'ohm": (1, 0, 'Ohm'),
 "'ounce": (1, 0, 'Ounce'),
 "'oz": (1, 0, 'Ounce'),
 "'pA": (1, 0, 'Picoampere'),
 "'pC": (1, 0, 'Picocoulomb'),
 "'pF": (1, 0, 'Picofarad'),
 "'pJ": (1, 0, 'pJ'),
 "'pN": (1, 0, 'pN'),
 "'pV": (1, 0, 'Picovolt'),
 "'pW": (1, 0, 'Picowatt'),
 "'pm": (1, 0, 'Picometer'),
 "'poise": (1, 0, 'Poise'),
 "'pound": (1, 0, 'Pound'),
 "'ppb": (1, 0, 'Parts per billion'),
 "'ppm": (1, 0, 'Parts per million'),
 "'ps": (1, 0, 'Picosecond'),
 "'psf": (1, 0, 'Pounds-force per square foot'),
 "'psi": (1, 0, 'Pounds-force per square inch'),
 "'rad": (1, 0, 'Radian'),
 "'radpm": (1, 0, 'Radians per minute'),
 "'rev": (1, 0, 'Revolution'),
 "'rph": (1, 0, 'Revolutions per hour'),
 "'rpm": (1, 0, 'Revolutions per minute'),
 "'s": (1, 0, 'Second'),
 "'sb": (1, 0, 'Stilb'),
 "'sec": (1, 0, 'Second'),
 "'slug": (1, 0, 'Slug'),
 "'sr": (1, 0, 'Steradian'),
 "'statC": (1, 0, 'Franklin (Statcoulomb)'),
 "'stokes": (1, 0, 'Stokes'),
 "'t": (1, 0, 'Metric ton'),
 "'tesla": (1, 0, 'Tesla'),
 "'ton": (1, 0, 'Ton'),
 "'tonf": (1, 0, 'Ton Force'),
 "'tonne": (1, 0, 'Metric ton'),
 "'tonnef": (1, 0, 'Metric Ton Force'),
 "'torr": (1, 0, 'Torr'),
 "'u": (1, 0, 'Unified atomic mass unit - dalton'),
 "'volt": (1, 0, 'Volt'),
 "'watt": (1, 0, 'Watt'),
 "'week": (1, 0, 'Week'),
 "'yd": (1, 0, 'Yard'),
 "'yr": (1, 0, 'Year'),
 "'¤": (1, 0, 'Default currency'),
 "'°": (1, 0, 'Degree'),
 "'°C": (1, 0, 'Celsius'),
 "'°F": (1, 0, 'Fahrenheit'),
 "'°Ra": (1, 0, 'Rankine'),
 "'°Re": (1, 0, 'Réaumur'),
 "'Δ°C": (1, 0, 'Change °C'),
 "'Δ°F": (1, 0, 'Change °F'),
 "'Δ°Re": (1, 0, 'Change °Re'),
 "'Ω": (1, 0, 'Ohm'),
 "'ε.0": (1, 0, 'Vacuum permittivity'),
 "'μ.0": (1, 0, 'Magnetic constant'),
 "'μA": (1, 0, 'Microampere'),
 "'μC": (1, 0, 'Microcoulomb'),
 "'μCi": (1, 0, 'Microcurie'),
 "'μF": (1, 0, 'Microfarad'),
 "'μH": (1, 0, 'Microhenry'),
 "'μJ": (1, 0, 'μJ'),
 "'μN": (1, 0, 'Micronewton'),
 "'μR": (1, 0, 'Microroentgen'),
 "'μT": (1, 0, 'μT'),
 "'μV": (1, 0, 'Microvolt'),
 "'μW": (1, 0, 'Microwatt'),
 "'μWb": (1, 0, 'μWb'),
 "'μg": (1, 0, 'Microgram'),
 "'μm": (1, 0, 'Micrometer'),
 "'μmol": (1, 0, 'Micromole'),
 "'μs": (1, 0, 'Microsecond'),
 "'‰": (1, 0, 'Per mille'),
 'Clear': (2,
           -1,
           '<strong>Clear</strong>(<span style="color: blue;">...</span>) — Clear all variables and '
           'functions except the initial ones.'),
 'Gamma': (2,
           1,
           '<strong>Gamma</strong>(<span style="color: blue;">&quot;number&quot;</span>) — Gamma function.'),
 'Im': (1,
        1,
        '<strong>Im</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
        'imaginary part of a complex number.'),
 'IsDefined': (2,
               1,
               '<strong>IsDefined</strong>(<span style="color: blue;">&quot;expression&quot;</span>) — '
               'Returns 1 if all variables and functions in the expression are defined, 0 - otherwise.'),
 'IsString': (2,
              1,
              '<strong>IsString</strong>(<span style="color: blue;">&quot;expression&quot;</span>) — Returns '
              '1 if specified argument is a string. Returns 0 otherwise.'),
 'Jacob': (2,
           2,
           '<strong>Jacob</strong>(<span style="color: blue;">&quot;1:vector&quot;</span>, <span '
           'style="color: blue;">&quot;2:vector&quot;</span>) — Returns the Jacobian matrix of the vector '
           'function <span style="color: blue;">&quot;1:vector&quot;</span>.'),
 'Re': (1,
        1,
        '<strong>Re</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the real '
        'part of a complex number.'),
 'Sleep': (2,
           1,
           '<strong>Sleep</strong>(<span style="color: blue;">&quot;number&quot;</span>) — Suspends the '
           'current thread for the specified amount of time specified in milliseconds.'),
 'UnitsOf': (2,
             1,
             '<strong>UnitsOf</strong>(<span style="color: blue;">&quot;argument&quot;</span>) — Returns the '
             'units of <span style="color: blue;">&quot;argument&quot;</span>. If <span style="color: '
             'blue;">&quot;argument&quot;</span> has no units, returns 1.'),
 'abs': (1,
         1,
         '<strong>abs</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Absolute '
         'value.'),
 'acos': (1,
          1,
          '<strong>acos</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
          'inverse cosine.'),
 'acosh': (1,
           1,
           '<strong>acosh</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns '
           'the inverse hyperbolic cosine.'),
 'acot': (1,
          1,
          '<strong>acot</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
          'inverse cotangent.'),
 'acoth': (1,
           1,
           '<strong>acoth</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns '
           'the inverse hyperbolic cotangent.'),
 'acsc': (1,
          1,
          '<strong>acsc</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
          'inverse cosecant.'),
 'ainterp': (1,
             3,
             '<strong>ainterp</strong>(<span style="color: blue;">&quot;1:argument&quot;</span>, <span '
             'style="color: blue;">&quot;2:argument&quot;</span>, <span style="color: '
             'blue;">&quot;3:argument&quot;</span>) — Returns an Akima-spline interpolated y-value at '
             'x=<span style="color: blue;">&quot;3:argument&quot;</span> for data vectors x-vector <span '
             'style="color: blue;">&quot;1:argument&quot;</span> and y-vector <span style="color: '
             'blue;">&quot;2:argument&quot;</span> of the same size. (A vector is a column matrix.)'),
 'alg': (1,
         3,
         '<strong>alg</strong>(<span style="color: blue;">&quot;1:matrix&quot;</span>, <span style="color: '
         'blue;">&quot;2:number&quot;</span>, <span style="color: blue;">&quot;3:number&quot;</span>) — '
         'Cofactor (algebraically signed minor) of matrix.'),
 'appVersion': (2,
                1,
                '<strong>appVersion</strong>(<span style="color: blue;">&quot;argument&quot;</span>) — '
                'Returns SMath Studio version. Supported values for <span style="color: '
                'blue;">&quot;argument&quot;</span> are from -4 to 4. Negative argument requests for version '
                'of the program which last saved a worksheet. Positive argument requests for current SMath '
                'Studio instance version.'),
 'arg': (1,
         1,
         '<strong>arg</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
         'angle from the real axis to the given complex number.'),
 'asec': (1,
          1,
          '<strong>asec</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
          'inverse secant.'),
 'asin': (1,
          1,
          '<strong>asin</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
          'inverse sine.'),
 'asinh': (1,
           1,
           '<strong>asinh</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns '
           'the inverse hyperbolic sine.'),
 'atan (1)': (1,
              1,
              '<strong>atan</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns '
              'the inverse tangent.'),
 'atan (2)': (1,
              2,
              '<strong>atan</strong>(<span style="color: blue;">&quot;1:complexNumber&quot;</span>, <span '
              'style="color: blue;">&quot;2:complexNumber&quot;</span>) — Returns the inverse tangent.'),
 'atanh': (1,
           1,
           '<strong>atanh</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns '
           'the inverse hyperbolic tangent.'),
 'augment': (1,
             -1,
             '<strong>augment</strong>(<span style="color: blue;">...</span>) — Returns a matrix formed by '
             'placing the arguments left to right. Arguments are matrices/vectors having the same number of '
             'rows, or they are scalars and row matrices.'),
 'break': (1,
           0,
           'Terminates the execution of the nearest enclosing loop in which it appears. Control passes to '
           'the statement that follows the terminated statement, if any.'),
 'ceil': (1,
          1,
          '<strong>ceil</strong>(<span style="color: blue;">&quot;number&quot;</span>) — The smallest '
          'integer that is greater than or equal to a given number.'),
 'cinterp': (1,
             3,
             '<strong>cinterp</strong>(<span style="color: blue;">&quot;1:argument&quot;</span>, <span '
             'style="color: blue;">&quot;2:argument&quot;</span>, <span style="color: '
             'blue;">&quot;3:argument&quot;</span>) — Returns a cubic-spline interpolated y-value at x=<span '
             'style="color: blue;">&quot;3:argument&quot;</span> for data vectors x-vector <span '
             'style="color: blue;">&quot;1:argument&quot;</span> and y-vector <span style="color: '
             'blue;">&quot;2:argument&quot;</span> of the same size. (A vector is a column matrix.)'),
 'col': (2,
         2,
         '<strong>col</strong>(<span style="color: blue;">&quot;1:matrix&quot;</span>, <span style="color: '
         'blue;">&quot;2:number&quot;</span>) — Returns the specified column <span style="color: '
         'blue;">&quot;2:number&quot;</span> of the matrix/vector <span style="color: '
         'blue;">&quot;1:matrix&quot;</span>.'),
 'cols': (2,
          1,
          '<strong>cols</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Returns the number '
          'of columns of the matrix/vector.'),
 'concat': (2,
            -1,
            '<strong>concat</strong>(<span style="color: blue;">...</span>) — Returns the string formed by '
            'concatenating the given strings.'),
 'continue': (1, 0, 'Ends the current iteration of a loop.'),
 'cos': (1,
         1,
         '<strong>cos</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
         'cosine.'),
 'cosh': (1,
          1,
          '<strong>cosh</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
          'hyperbolic cosine.'),
 'cot': (1,
         1,
         '<strong>cot</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
         'cotangent.'),
 'coth': (1,
          1,
          '<strong>coth</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
          'hyperbolic cotangent.'),
 'csc': (1,
         1,
         '<strong>csc</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
         'cosecant.'),
 'csch': (1,
          1,
          '<strong>csch</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
          'hyperbolic cosecant.'),
 'csort': (1,
           2,
           '<strong>csort</strong>(<span style="color: blue;">&quot;1:matrix&quot;</span>, <span '
           'style="color: blue;">&quot;2:number&quot;</span>) — Returns a matrix/vector <span style="color: '
           'blue;">&quot;1:matrix&quot;</span> formed by rearranging rows until specified column <span '
           'style="color: blue;">&quot;2:number&quot;</span> is in ascending order.'),
 'description': (2,
                 1,
                 '<strong>description</strong>(<span style="color: blue;">&quot;name&quot;</span>) — Returns '
                 'Description text of the definition <span style="color: blue;">&quot;name&quot;</span> '
                 'using current language.'),
 'det': (1,
         1,
         '<strong>det</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Matrix determinant.'),
 'dfile': (2,
           1,
           '<strong>dfile</strong>(<span style="color: blue;">&quot;fileName&quot;</span>) — Remove file '
           'from file system, if such file exists. The function returns &apos;1&apos; if successful, '
           'otherwise &apos;0&apos;.'),
 'diag': (1,
          1,
          '<strong>diag</strong>(<span style="color: blue;">&quot;number&quot;</span>) — Returns a square '
          'matrix containing on its diagonal the elements of the given vector (a vector is a column '
          'matrix).'),
 'diff (2)': (2,
              2,
              '<strong>diff</strong>(<span style="color: blue;">&quot;1:expression&quot;</span>, <span '
              'style="color: blue;">&quot;2:variable&quot;</span>) — Finds the derivative of expression '
              '<span style="color: blue;">&quot;1:expression&quot;</span> relative to variable <span '
              'style="color: blue;">&quot;2:variable&quot;</span>.'),
 'diff (3)': (2,
              3,
              '<strong>diff</strong>(<span style="color: blue;">&quot;1:expression&quot;</span>, <span '
              'style="color: blue;">&quot;2:variable&quot;</span>, <span style="color: '
              'blue;">&quot;3:number&quot;</span>) — Finds the order <span style="color: '
              'blue;">&quot;3:number&quot;</span> derivative of expression <span style="color: '
              'blue;">&quot;1:expression&quot;</span> relative to variable <span style="color: '
              'blue;">&quot;2:variable&quot;</span>.'),
 'e': (1, 0, "Number 'e'"),
 'el (2)': (1,
            2,
            '<strong>el</strong>(<span style="color: blue;">&quot;1:vector&quot;</span>, <span style="color: '
            'blue;">&quot;2:number&quot;</span>) — Returns the specified element <span style="color: '
            'blue;">&quot;2:number&quot;</span> of the vector <span style="color: '
            'blue;">&quot;1:vector&quot;</span>.'),
 'el (3)': (1,
            3,
            '<strong>el</strong>(<span style="color: blue;">&quot;1:matrix&quot;</span>, <span style="color: '
            'blue;">&quot;2:number&quot;</span>, <span style="color: blue;">&quot;3:number&quot;</span>) — '
            'Returns the element of the matrix <span style="color: blue;">&quot;1:matrix&quot;</span> in the '
            'row <span style="color: blue;">&quot;2:number&quot;</span> and column <span style="color: '
            'blue;">&quot;3:number&quot;</span>.'),
 'error': (2,
           1,
           '<strong>error</strong>(<span style="color: blue;">&quot;string&quot;</span>) — Shows standard '
           'SMath Studio error tip with text from the function&apos;s argument.'),
 'eval': (2,
          1,
          '<strong>eval</strong>(<span style="color: blue;">&quot;expression&quot;</span>) — Converts the '
          'given expression from symbolic to numeric notation.'),
 'exp': (1,
         1,
         '<strong>exp</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
         'exponential function, e raised to the power <span style="color: '
         'blue;">&quot;complexNumber&quot;</span>.'),
 'findrows': (2,
              3,
              '<strong>findrows</strong>(<span style="color: blue;">&quot;1:matrix&quot;</span>, <span '
              'style="color: blue;">&quot;2:expression&quot;</span>, <span style="color: '
              'blue;">&quot;3:number&quot;</span>) — Retrieves all rows of the <span style="color: '
              'blue;">&quot;1:matrix&quot;</span> where <span style="color: '
              'blue;">&quot;2:expression&quot;</span> exists in column <span style="color: '
              'blue;">&quot;3:number&quot;</span>. Returns 0 if no matches found.'),
 'findstr': (2,
             2,
             '<strong>findstr</strong>(<span style="color: blue;">&quot;1:string&quot;</span>, <span '
             'style="color: blue;">&quot;2:string&quot;</span>) — Returns a vector (a column matrix) of the '
             'start positions of string <span style="color: blue;">&quot;2:string&quot;</span> within string '
             '<span style="color: blue;">&quot;1:string&quot;</span>, or -1 if no matches found.'),
 'floor': (1,
           1,
           '<strong>floor</strong>(<span style="color: blue;">&quot;number&quot;</span>) — The greatest '
           'integer that is less than or equal to a given number.'),
 'for (3)': (2,
             3,
             '<strong>for</strong>(<span style="color: blue;">&quot;1:increment&quot;</span>, <span '
             'style="color: blue;">&quot;2:expression&quot;</span>, <span style="color: '
             'blue;">&quot;3:expression&quot;</span>) — For loop. The function of controlled iterations. The '
             'cycle repeats <span style="color: blue;">&quot;3:expression&quot;</span>, while <span '
             'style="color: blue;">&quot;1:increment&quot;</span> uses all the values from <span '
             'style="color: blue;">&quot;2:expression&quot;</span>. Repeating expressions can be set to any '
             'number of expressions.'),
 'for (4)': (2,
             4,
             '<strong>for</strong>(<span style="color: blue;">&quot;1:increment&quot;</span>, <span '
             'style="color: blue;">&quot;2:condition&quot;</span>, <span style="color: '
             'blue;">&quot;3:expression&quot;</span>, <span style="color: '
             'blue;">&quot;4:expression&quot;</span>) — For loop. The function of controlled iterations. The '
             'cycle repeats <span style="color: blue;">&quot;4:expression&quot;</span>, while <span '
             'style="color: blue;">&quot;1:increment&quot;</span> satisfies the condition <span '
             'style="color: blue;">&quot;2:condition&quot;</span> and after each passage necessarily '
             'satisfied <span style="color: blue;">&quot;3:expression&quot;</span>. Repeating expressions '
             'can be set to any number of expressions.'),
 'i': (1, 0, 'Imaginary unit'),
 'identity': (1,
              1,
              '<strong>identity</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Returns an '
              'n x n identity matrix (a matrix of 0&apos;s with 1&apos;s along the diagonal). <span '
              'style="color: blue;">&quot;matrix&quot;</span> must be a positive integer.'),
 'if': (2,
        -1,
        '<strong>if</strong>(<span style="color: blue;">...</span>) — The IF construct allow execution of a '
        'statement or series of statements if the calculated expression is equal to 1 (true), or of a '
        'separate set of statements if it is 0 (false).'),
 'importData (1)': (2,
                    1,
                    '<strong>importData</strong>(<span style="color: blue;">&quot;fileName&quot;</span>) — '
                    'Returns a matrix of loaded data from specified file using default parsing parameters.'),
 'importData (9)': (2,
                    9,
                    '<strong>importData</strong>(<span style="color: blue;">&quot;1:fileName&quot;</span>, '
                    '<span style="color: blue;">&quot;2:delimiter&quot;</span>, <span style="color: '
                    'blue;">&quot;3:delimiter&quot;</span>, <span style="color: '
                    'blue;">&quot;4:delimiter&quot;</span>, <span style="color: '
                    'blue;">&quot;5:number&quot;</span>, <span style="color: '
                    'blue;">&quot;6:number&quot;</span>, <span style="color: '
                    'blue;">&quot;7:number&quot;</span>, <span style="color: '
                    'blue;">&quot;8:number&quot;</span>, <span style="color: '
                    'blue;">&quot;9:number&quot;</span>) — Returns a matrix of loaded data from specified '
                    'file <span style="color: blue;">&quot;1:fileName&quot;</span>. Function can be used '
                    'with 1-9 of the arguments specified. Digit 0 (zero) can be used for the arguments '
                    '(except <span style="color: blue;">&quot;1:fileName&quot;</span>) to get the built-in '
                    'default values. Function is able to read data with manually specified Decimal Symbol '
                    '(<span style="color: blue;">&quot;2:delimiter&quot;</span>), Arguments Separator (<span '
                    'style="color: blue;">&quot;3:delimiter&quot;</span>) and columns delimiters (<span '
                    'style="color: blue;">&quot;4:delimiter&quot;</span>). To read a specific region of the '
                    'data file rows an columns ranges can be requested (<span style="color: '
                    'blue;">&quot;5:number&quot;</span> - start row, <span style="color: '
                    'blue;">&quot;6:number&quot;</span> - end row, <span style="color: '
                    'blue;">&quot;7:number&quot;</span> - start column, <span style="color: '
                    'blue;">&quot;8:number&quot;</span> - end column). To read a data represented '
                    'symbolically <span style="color: blue;">&quot;9:number&quot;</span> can be set to 1.'),
 'int': (2,
         4,
         '<strong>int</strong>(<span style="color: blue;">&quot;1:expression&quot;</span>, <span '
         'style="color: blue;">&quot;2:variable&quot;</span>, <span style="color: '
         'blue;">&quot;3:number&quot;</span>, <span style="color: blue;">&quot;4:number&quot;</span>) — '
         'Definite integral of an expression <span style="color: blue;">&quot;1:expression&quot;</span> with '
         'independent variable <span style="color: blue;">&quot;2:variable&quot;</span>. <span style="color: '
         'blue;">&quot;3:number&quot;</span>-lower limit, <span style="color: '
         'blue;">&quot;4:number&quot;</span>-upper limit.'),
 'invert': (1,
            1,
            '<strong>invert</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Inverted '
            'value.'),
 'lastError': (1, 0, 'Text of the last detected calculation error.'),
 'length': (2,
            1,
            '<strong>length</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Returns the '
            'number of elements in the matrix or vector. Returns a scalar.'),
 'line': (2,
          -1,
          '<strong>line</strong>(<span style="color: blue;">...</span>) — For grouping 2 or more lines of '
          'code into a block.'),
 'linterp': (1,
             3,
             '<strong>linterp</strong>(<span style="color: blue;">&quot;1:argument&quot;</span>, <span '
             'style="color: blue;">&quot;2:argument&quot;</span>, <span style="color: '
             'blue;">&quot;3:argument&quot;</span>) — Returns a linearly interpolated y-value at x=<span '
             'style="color: blue;">&quot;3:argument&quot;</span> for data vectors x-vector <span '
             'style="color: blue;">&quot;1:argument&quot;</span> and y-vector <span style="color: '
             'blue;">&quot;2:argument&quot;</span> of the same size. (A vector is a column matrix.)'),
 'ln': (1,
        1,
        '<strong>ln</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Natural '
        'logarithm.'),
 'log': (1,
         2,
         '<strong>log</strong>(<span style="color: blue;">&quot;1:number&quot;</span>, <span style="color: '
         'blue;">&quot;2:number&quot;</span>) — Returns the logarithm of <span style="color: '
         'blue;">&quot;1:number&quot;</span> to the specified base <span style="color: '
         'blue;">&quot;2:number&quot;</span>.'),
 'log10': (1,
           1,
           '<strong>log10</strong>(<span style="color: blue;">&quot;number&quot;</span>) — Returns the base '
           '10 logarithm of a number.'),
 'mat': (1, -1, '<strong>mat</strong>(<span style="color: blue;">...</span>) — Matrix.'),
 'matrix': (1,
            2,
            '<strong>matrix</strong>(<span style="color: blue;">&quot;1:number&quot;</span>, <span '
            'style="color: blue;">&quot;2:number&quot;</span>) — Returns a zero matrix of the specified size '
            '<span style="color: blue;">&quot;1:number&quot;</span>-rows, <span style="color: '
            'blue;">&quot;2:number&quot;</span>-columns.'),
 'max': (1,
         1,
         '<strong>max</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Returns the largest '
         'element of vector or matrix. If any value is complex, returns max(Re(...)) + i*max(Im(...)).'),
 'min': (1,
         1,
         '<strong>min</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Returns the smallest '
         'element of vector or matrix. If any value is complex, returns min(Re(...)) + i*min(Im(...)).'),
 'minor': (1,
           3,
           '<strong>minor</strong>(<span style="color: blue;">&quot;1:matrix&quot;</span>, <span '
           'style="color: blue;">&quot;2:number&quot;</span>, <span style="color: '
           'blue;">&quot;3:number&quot;</span>) — Minor of matrix.'),
 'mixed': (1,
           3,
           '<strong>mixed</strong>(<span style="color: blue;">&quot;1:number&quot;</span>, <span '
           'style="color: blue;">&quot;2:number&quot;</span>, <span style="color: '
           'blue;">&quot;3:number&quot;</span>) — Mixed number.'),
 'mod': (1,
         2,
         '<strong>mod</strong>(<span style="color: blue;">&quot;1:number&quot;</span>, <span style="color: '
         'blue;">&quot;2:number&quot;</span>) — Returns the remainder on dividing the <span style="color: '
         'blue;">&quot;1:number&quot;</span> by <span style="color: blue;">&quot;2:number&quot;</span>. '
         'Arguments must be real.'),
 'norm1': (1,
           1,
           '<strong>norm1</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Returns the L1 '
           'norm of the matrix.'),
 'norme': (1,
           1,
           '<strong>norme</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Returns the '
           'Euclidean norm of the matrix.'),
 'normi': (1,
           1,
           '<strong>normi</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Returns the '
           'infinity norm of the matrix.'),
 'nthroot': (1,
             2,
             '<strong>nthroot</strong>(<span style="color: blue;">&quot;1:complexNumber&quot;</span>, <span '
             'style="color: blue;">&quot;2:complexNumber&quot;</span>) — Root.'),
 'num2str (1)': (2,
                 1,
                 '<strong>num2str</strong>(<span style="color: blue;">&quot;expression&quot;</span>) — '
                 'Converts specified math expression to a string.'),
 'num2str (2)': (2,
                 2,
                 '<strong>num2str</strong>(<span style="color: blue;">&quot;1:expression&quot;</span>, <span '
                 'style="color: blue;">&quot;2:string&quot;</span>) — Converts specified math expression to '
                 'a string.'),
 'numden': (1,
            1,
            '<strong>numden</strong>(<span style="color: blue;">&quot;expression&quot;</span>) — Returns a '
            '2-element vector (2x1 matrix) of the numerator and denominator of <span style="color: '
            'blue;">&quot;expression&quot;</span>.'),
 'perc': (1,
          2,
          '<strong>perc</strong>(<span style="color: blue;">&quot;1:number&quot;</span>, <span style="color: '
          'blue;">&quot;2:number&quot;</span>) — Percent. For example, if <span style="color: '
          'blue;">&quot;2:number&quot;</span> is 5 and <span style="color: '
          'blue;">&quot;1:number&quot;</span> is 100, then this function returns 5% of 100.'),
 'pol2xy': (1,
            2,
            '<strong>pol2xy</strong>(<span style="color: blue;">&quot;1:argument&quot;</span>, <span '
            'style="color: blue;">&quot;2:argument&quot;</span>) — Converts the polar coordinates of a point '
            'in 2D space to rectangular coordinates.'),
 'polyroots': (1,
               1,
               '<strong>polyroots</strong>(<span style="color: blue;">&quot;vector&quot;</span>) — Returns '
               'the roots of the polynomial whose coefficients are in <span style="color: '
               'blue;">&quot;vector&quot;</span>.'),
 'product': (2,
             4,
             '<strong>product</strong>(<span style="color: blue;">&quot;1:expression&quot;</span>, <span '
             'style="color: blue;">&quot;2:increment&quot;</span>, <span style="color: '
             'blue;">&quot;3:number&quot;</span>, <span style="color: blue;">&quot;4:number&quot;</span>) — '
             'Iterated product. Product of an expression <span style="color: '
             'blue;">&quot;1:expression&quot;</span> in variable <span style="color: '
             'blue;">&quot;2:increment&quot;</span> with lower limit <span style="color: '
             'blue;">&quot;3:number&quot;</span> and upper limit <span style="color: '
             'blue;">&quot;4:number&quot;</span>.'),
 'random': (1,
            1,
            '<strong>random</strong>(<span style="color: blue;">&quot;number&quot;</span>) — Returns a '
            'random number within the range of 0 to <span style="color: blue;">&quot;number&quot;</span>. '
            'Results are uniformly distributed within the range.'),
 'range (2)': (2,
               2,
               '<strong>range</strong>(<span style="color: blue;">&quot;1:number&quot;</span>, <span '
               'style="color: blue;">&quot;2:number&quot;</span>) — Returns a vector (column matrix) of '
               'values within the range of <span style="color: blue;">&quot;1:number&quot;</span> to <span '
               'style="color: blue;">&quot;2:number&quot;</span>, inclusive. Each value is obtained by '
               'adding a step equal to 1 to the previous value, starting with <span style="color: '
               'blue;">&quot;1:number&quot;</span>. <span style="color: blue;">&quot;2:number&quot;</span> '
               'does not necessarily appear in the output vector.'),
 'range (3)': (2,
               3,
               '<strong>range</strong>(<span style="color: blue;">&quot;1:number&quot;</span>, <span '
               'style="color: blue;">&quot;2:number&quot;</span>, <span style="color: '
               'blue;">&quot;3:number&quot;</span>) — Returns a vector (column matrix) of values within the '
               'range of <span style="color: blue;">&quot;1:number&quot;</span> to <span style="color: '
               'blue;">&quot;2:number&quot;</span>, inclusive. Each value is obtained by adding a difference '
               'between <span style="color: blue;">&quot;3:number&quot;</span> and <span style="color: '
               'blue;">&quot;1:number&quot;</span>. <span style="color: blue;">&quot;2:number&quot;</span> '
               'does not necessarily appear in the output vector.'),
 'rank': (1, 1, '<strong>rank</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Matrix rank.'),
 'reverse': (1,
             1,
             '<strong>reverse</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Reverses the '
             'order of rows in a matrix, or of elements in a vector. (A vector is a column matrix.)'),
 'rfile': (2,
           1,
           '<strong>rfile</strong>(<span style="color: blue;">&quot;fileName&quot;</span>) — Read math '
           'expression from file, if such file exists. Often returns symbolic result.'),
 'roots (2)': (2,
               2,
               '<strong>roots</strong>(<span style="color: blue;">&quot;1:vector&quot;</span>, <span '
               'style="color: blue;">&quot;2:vector&quot;</span>) — Finds roots for system of nonlinear '
               'equations. Returns the values of <span style="color: blue;">&quot;2:vector&quot;</span> to '
               'make the set of functions <span style="color: blue;">&quot;1:vector&quot;</span> equal to '
               'zeros.'),
 'roots (3)': (2,
               3,
               '<strong>roots</strong>(<span style="color: blue;">&quot;1:vector&quot;</span>, <span '
               'style="color: blue;">&quot;2:vector&quot;</span>, <span style="color: '
               'blue;">&quot;3:vector&quot;</span>) — Finds roots for system of nonlinear equations '
               'according to specified approaches <span style="color: blue;">&quot;3:vector&quot;</span>. '
               'Returns the value of <span style="color: blue;">&quot;2:vector&quot;</span> to make the set '
               'of functions <span style="color: blue;">&quot;1:vector&quot;</span> equal to zeros.'),
 'round (2)': (1,
               2,
               '<strong>round</strong>(<span style="color: blue;">&quot;1:number&quot;</span>, <span '
               'style="color: blue;">&quot;2:number&quot;</span>) — Rounds the real number <span '
               'style="color: blue;">&quot;1:number&quot;</span> to <span style="color: '
               'blue;">&quot;2:number&quot;</span> places.'),
 'round (3)': (1,
               3,
               '<strong>round</strong>(<span style="color: blue;">&quot;1:number&quot;</span>, <span '
               'style="color: blue;">&quot;2:number&quot;</span>, <span style="color: '
               'blue;">&quot;3:string&quot;</span>) — Rounds the real number <span style="color: '
               'blue;">&quot;1:number&quot;</span> to <span style="color: blue;">&quot;2:number&quot;</span> '
               'places.'),
 'row': (2,
         2,
         '<strong>row</strong>(<span style="color: blue;">&quot;1:matrix&quot;</span>, <span style="color: '
         'blue;">&quot;2:number&quot;</span>) — Returns the specified row <span style="color: '
         'blue;">&quot;2:number&quot;</span> of the matrix/vector <span style="color: '
         'blue;">&quot;1:matrix&quot;</span>.'),
 'rows': (2,
          1,
          '<strong>rows</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Returns the number '
          'of rows of the matrix/vector.'),
 'rsort': (1,
           2,
           '<strong>rsort</strong>(<span style="color: blue;">&quot;1:matrix&quot;</span>, <span '
           'style="color: blue;">&quot;2:number&quot;</span>) — Returns a matrix/vector <span style="color: '
           'blue;">&quot;1:matrix&quot;</span> formed by rearranging columns until specified row <span '
           'style="color: blue;">&quot;2:number&quot;</span> is in ascending order.'),
 'sec': (1,
         1,
         '<strong>sec</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
         'secant.'),
 'sech': (1,
          1,
          '<strong>sech</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
          'hyperbolic secant.'),
 'sign': (1,
          1,
          '<strong>sign</strong>(<span style="color: blue;">&quot;number&quot;</span>) — Returns 0 if x=0, 1 '
          'if x&gt;0, and -1 otherwise. Argument must be a real number.'),
 'sin': (1,
         1,
         '<strong>sin</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
         'sine.'),
 'sinh': (1,
          1,
          '<strong>sinh</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
          'hyperbolic sine.'),
 'solve (2)': (2,
               2,
               '<strong>solve</strong>(<span style="color: blue;">&quot;1:expression&quot;</span>, <span '
               'style="color: blue;">&quot;2:variable&quot;</span>) — Returns real roots of expression <span '
               'style="color: blue;">&quot;1:expression&quot;</span> with respect to variable <span '
               'style="color: blue;">&quot;2:variable&quot;</span>.'),
 'solve (4)': (2,
               4,
               '<strong>solve</strong>(<span style="color: blue;">&quot;1:expression&quot;</span>, <span '
               'style="color: blue;">&quot;2:variable&quot;</span>, <span style="color: '
               'blue;">&quot;3:number&quot;</span>, <span style="color: blue;">&quot;4:number&quot;</span>) '
               '— Returns real roots of expression <span style="color: '
               'blue;">&quot;1:expression&quot;</span> with respect to variable <span style="color: '
               'blue;">&quot;2:variable&quot;</span> in the interval between <span style="color: '
               'blue;">&quot;3:number&quot;</span> and <span style="color: '
               'blue;">&quot;4:number&quot;</span>.'),
 'sort': (1,
          1,
          '<strong>sort</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Returns a vector '
          'with the values sorted in ascending order. (A vector is a column matrix.)'),
 'sqrt': (1,
          1,
          '<strong>sqrt</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Square '
          'root.'),
 'stack': (1,
           -1,
           '<strong>stack</strong>(<span style="color: blue;">...</span>) — Returns an array formed by '
           'placing arguments top to bottom. Arguments are matrices/vectors having the same number of '
           'columns, or they are scalars and vectors. (A vector is a column matrix.)'),
 'str2num': (2,
             1,
             '<strong>str2num</strong>(<span style="color: blue;">&quot;string&quot;</span>) — Returns math '
             'expression formed by converting from specified string.'),
 'strlen': (2,
            1,
            '<strong>strlen</strong>(<span style="color: blue;">&quot;string&quot;</span>) — Returns the '
            'number of characters in specified string.'),
 'strrep': (2,
            3,
            '<strong>strrep</strong>(<span style="color: blue;">&quot;1:string&quot;</span>, <span '
            'style="color: blue;">&quot;2:string&quot;</span>, <span style="color: '
            'blue;">&quot;3:string&quot;</span>) — Replaces all occurrences of the string <span '
            'style="color: blue;">&quot;2:string&quot;</span> within string <span style="color: '
            'blue;">&quot;1:string&quot;</span> with the string <span style="color: '
            'blue;">&quot;3:string&quot;</span>.'),
 'submatrix': (1,
               5,
               '<strong>submatrix</strong>(<span style="color: blue;">&quot;1:matrix&quot;</span>, <span '
               'style="color: blue;">&quot;2:argument&quot;</span>, <span style="color: '
               'blue;">&quot;3:argument&quot;</span>, <span style="color: '
               'blue;">&quot;4:argument&quot;</span>, <span style="color: '
               'blue;">&quot;5:argument&quot;</span>) — Returns the submatrix consisting of elements in rows '
               '<span style="color: blue;">&quot;2:argument&quot;</span> through <span style="color: '
               'blue;">&quot;3:argument&quot;</span> and columns <span style="color: '
               'blue;">&quot;4:argument&quot;</span> through <span style="color: '
               'blue;">&quot;5:argument&quot;</span>.'),
 'substr (2)': (2,
                2,
                '<strong>substr</strong>(<span style="color: blue;">&quot;1:string&quot;</span>, <span '
                'style="color: blue;">&quot;2:number&quot;</span>) — Returns a substring of <span '
                'style="color: blue;">&quot;1:string&quot;</span>. <span style="color: '
                'blue;">&quot;2:number&quot;</span> is a starting character position of substring.'),
 'substr (3)': (2,
                3,
                '<strong>substr</strong>(<span style="color: blue;">&quot;1:string&quot;</span>, <span '
                'style="color: blue;">&quot;2:number&quot;</span>, <span style="color: '
                'blue;">&quot;3:number&quot;</span>) — Returns a substring of <span style="color: '
                'blue;">&quot;1:string&quot;</span>. Where <span style="color: '
                'blue;">&quot;2:number&quot;</span> is a starting character position of substring; <span '
                'style="color: blue;">&quot;3:number&quot;</span> is a length of result string.'),
 'sum (1)': (2,
             1,
             '<strong>sum</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Summation of the '
             'vector/matrix elements.'),
 'sum (4)': (2,
             4,
             '<strong>sum</strong>(<span style="color: blue;">&quot;1:expression&quot;</span>, <span '
             'style="color: blue;">&quot;2:increment&quot;</span>, <span style="color: '
             'blue;">&quot;3:number&quot;</span>, <span style="color: blue;">&quot;4:number&quot;</span>) — '
             'Summation of an expression <span style="color: blue;">&quot;1:expression&quot;</span> in '
             'summation variable <span style="color: blue;">&quot;2:increment&quot;</span> with lower limit '
             '<span style="color: blue;">&quot;3:number&quot;</span> and upper limit <span style="color: '
             'blue;">&quot;4:number&quot;</span>.'),
 'sys': (1,
         -1,
         '<strong>sys</strong>(<span style="color: blue;">...</span>) — System of values or equations.'),
 'tan': (1,
         1,
         '<strong>tan</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
         'tangent.'),
 'tanh': (1,
          1,
          '<strong>tanh</strong>(<span style="color: blue;">&quot;complexNumber&quot;</span>) — Returns the '
          'hyperbolic tangent.'),
 'time': (2,
          1,
          '<strong>time</strong>(<span style="color: blue;">&quot;argument&quot;</span>) — Returns the '
          'number of milliseconds that have elapsed since 12:00 midnight, January 1, 1601 A.D.'),
 'tr': (1,
        1,
        '<strong>tr</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Matrix trace - sum of '
        'the elements on the main diagonal (the diagonal from the upper left to the lower right) of a square '
        'matrix.'),
 'trace': (2,
           -1,
           '<strong>trace</strong>(<span style="color: blue;">...</span>) — Returns a string containing the '
           'value of the arguments with output order and surrounding text specified by first argument. '
           'Outputs values in the Output Window. Specifying of the first text argument is optional.'),
 'transpose': (2,
               1,
               '<strong>transpose</strong>(<span style="color: blue;">&quot;matrix&quot;</span>) — Matrix '
               'transpose.'),
 'trunc': (1,
           1,
           '<strong>trunc</strong>(<span style="color: blue;">&quot;number&quot;</span>) — Returns the '
           'integer part of a real number <span style="color: blue;">&quot;number&quot;</span> by removing '
           'the fractional part.'),
 'try': (2,
         2,
         '<strong>try</strong>(<span style="color: blue;">&quot;1:argument&quot;</span>, <span style="color: '
         'blue;">&quot;2:argument&quot;</span>) — Try/on error statement. The function evaluates and returns '
         '<span style="color: blue;">&quot;1:argument&quot;</span>. If <span style="color: '
         'blue;">&quot;1:argument&quot;</span> throws an error, the function evaluates and returns <span '
         'style="color: blue;">&quot;2:argument&quot;</span>.'),
 'vectorize': (2,
               1,
               '<strong>vectorize</strong>(<span style="color: blue;">&quot;expression&quot;</span>) — '
               'Allows to perform the same operation on each element of a vector, matrix or system.'),
 'vminor': (1,
            3,
            '<strong>vminor</strong>(<span style="color: blue;">&quot;1:matrix&quot;</span>, <span '
            'style="color: blue;">&quot;2:number&quot;</span>, <span style="color: '
            'blue;">&quot;3:number&quot;</span>) — Returns submatrix with the specified row (<span '
            'style="color: blue;">&quot;2:number&quot;</span>) and column (<span style="color: '
            'blue;">&quot;3:number&quot;</span>) removed from the given matrix (<span style="color: '
            'blue;">&quot;1:matrix&quot;</span>).'),
 'wfile': (2,
           2,
           '<strong>wfile</strong>(<span style="color: blue;">&quot;1:expression&quot;</span>, <span '
           'style="color: blue;">&quot;2:fileName&quot;</span>) — Write math expression <span style="color: '
           'blue;">&quot;1:expression&quot;</span> to a file <span style="color: '
           'blue;">&quot;2:fileName&quot;</span>. If a file with the given <span style="color: '
           'blue;">&quot;2:fileName&quot;</span> exists, it will be overwritten. The function returns '
           '&apos;1&apos; if successful, otherwise &apos;0&apos;.'),
 'while': (2,
           2,
           '<strong>while</strong>(<span style="color: blue;">&quot;1:condition&quot;</span>, <span '
           'style="color: blue;">&quot;2:expression&quot;</span>) — A function for iterating. The loop body, '
           '<span style="color: blue;">&quot;2:expression&quot;</span> is repeatedly executed as long as the '
           'condition <span style="color: blue;">&quot;1:condition&quot;</span> is true. Multiple '
           'expressions can be included in <span style="color: blue;">&quot;2:expression&quot;</span> by '
           'means of the line(...) function.'),
 'xy2pol': (1,
            2,
            '<strong>xy2pol</strong>(<span style="color: blue;">&quot;1:argument&quot;</span>, <span '
            'style="color: blue;">&quot;2:argument&quot;</span>) — Converts the rectangular coordinates of a '
            'point in 2D space to polar coordinates.'),
 'π': (1, 0, "Number 'Pi'"),
 '∞': (1, 0, 'Positive infinity')}
