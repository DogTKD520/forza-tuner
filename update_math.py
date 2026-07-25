import re

def update_math(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        math_py = f.read()

    # In _analyze_front_axle:
    math_py = math_py.replace("setup.tire_pressure_front,", "setup.tire_pressure_front.current,")
    math_py = math_py.replace("setup.camber_front,", "setup.camber_front.current,")
    
    # In _analyze_rear_axle:
    math_py = math_py.replace("setup.tire_pressure_rear,", "setup.tire_pressure_rear.current,")
    math_py = math_py.replace("setup.camber_rear,", "setup.camber_rear.current,")
    
    # Wait, the signature of _pressure_adjustment and _camber_adjustment needs updating?
    # No, they take `current_psi: float` and `current_camber: float`, which is correct.
    # But wait, what about bounding? 
    # Let's change them to take BoundValue instead of floats.
    # Let's rewrite `math_analyzer.py` completely since the clamping logic needs to be updated.

    pass

update_math('app/analysis/math_analyzer.py')
