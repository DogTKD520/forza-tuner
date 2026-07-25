import re

def update_routes(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        routes = f.read()

    # 1. Define BoundValue
    bound_value_def = """
class BoundValue(BaseModel):
    min: Optional[float] = None
    current: float
    max: Optional[float] = None
"""
    routes = routes.replace("class SetupCreateRequest(BaseModel):", bound_value_def + "\nclass SetupCreateRequest(BaseModel):")

    # 2. Update SetupCreateRequest
    # Replace floats with BoundValue for tunables
    tunables = [
        'tire_pressure_front', 'tire_pressure_rear', 'camber_front', 'camber_rear',
        'springs_front', 'springs_rear', 'arb_front', 'arb_rear', 'bump_front', 'bump_rear',
        'rebound_front', 'rebound_rear', 'front_weight_pct', 'aero_front', 'aero_rear',
        'final_drive', 'gear_1', 'gear_2', 'gear_3', 'gear_4', 'gear_5', 'gear_6',
        'gear_7', 'gear_8', 'gear_9', 'gear_10', 'toe_front', 'toe_rear', 'caster_front',
        'ride_height_front', 'ride_height_rear', 'downforce_front', 'downforce_rear',
        'brake_balance', 'brake_pressure', 'diff_front_accel', 'diff_front_decel',
        'diff_rear_accel', 'diff_rear_decel', 'diff_center_balance'
    ]

    for t in tunables:
        # Some have defaults like: `bump_front: float = 5.0`
        routes = re.sub(rf'\b{t}:\s*float(\s*=\s*[0-9\.]+)?', rf'{t}: BoundValue', routes)

    routes = routes.replace('diff_upgrade_type: str = "Race"', 'suspension_type: str = "Race"\n    diff_upgrade_type: str = "Race"')

    # 3. Update create_setup logic
    # Find VehicleSetup instantiation
    setup_instantiation = re.search(r'setup = VehicleSetup\(\s*vehicle_id=body.vehicle_id,.*?tuning_goal=body.tuning_goal or "street_road",\s*\)', routes, re.DOTALL)
    if setup_instantiation:
        inst_str = setup_instantiation.group(0)
        
        # We want to replace the fields that are now in tunables with a dict
        new_inst = """setup = VehicleSetup(
        vehicle_id=body.vehicle_id,
        user_id="",
        name=body.name,
        pi_rating=body.pi_rating,
        hp=body.hp,
        weight_lbs=body.weight_lbs,
        tire_compound=body.tire_compound,
        lock_tire_compound=body.lock_tire_compound,
        tuneable_springs=body.tuneable_springs,
        tuneable_arbs=body.tuneable_arbs,
        tuneable_dampers=body.tuneable_dampers,
        tuneable_aero_front=body.tuneable_aero_front,
        tuneable_aero_rear=body.tuneable_aero_rear,
        suspension_type=body.suspension_type,
        diff_upgrade_type=body.diff_upgrade_type,
        drivetrain=body.drivetrain,
        tuning_goal=body.tuning_goal or "street_road",
    )
    setup.tunables = {
"""
        for t in tunables:
            new_inst += f'        "{t}": body.{t}.model_dump(),\n'
        new_inst += "    }"

        routes = routes.replace(inst_str, new_inst)

    # 4. Update SetupSnapshot instantiation in analyze_session
    snap_instantiation = re.search(r'setup_snapshot = SetupSnapshot\(\s*tire_pressure_front=.*?tuning_goal=active_goal,\s*\)', routes, re.DOTALL)
    if snap_instantiation:
        # the db_setup now has .tunables (a dict)
        new_snap = """    tunables = db_setup.tunables
    setup_snapshot = SetupSnapshot(
        pi_rating=getattr(db_setup, "pi_rating", 700),
        hp=getattr(db_setup, "hp", 400),
        weight_lbs=getattr(db_setup, "weight_lbs", 3000.0),
        tire_compound=getattr(db_setup, "tire_compound", "Sport"),
        lock_tire_compound=getattr(db_setup, "lock_tire_compound", False),
        tuneable_springs=getattr(db_setup, "tuneable_springs", True),
        tuneable_arbs=getattr(db_setup, "tuneable_arbs", True),
        tuneable_dampers=getattr(db_setup, "tuneable_dampers", True),
        tuneable_aero_front=getattr(db_setup, "tuneable_aero_front", True),
        tuneable_aero_rear=getattr(db_setup, "tuneable_aero_rear", True),
        suspension_type=getattr(db_setup, "suspension_type", "Race"),
        diff_upgrade_type=getattr(db_setup, "diff_upgrade_type", "Race"),
        drivetrain=getattr(db_setup, "drivetrain", "AWD"),
        tuning_goal=active_goal,
"""
        for t in tunables:
            # We need to construct BoundValue objects for SetupSnapshot
            new_snap += f'        {t}=BoundValue(**tunables.get("{t}", {{"current": 0.0}})),\n'
        new_snap += "    )"
        routes = routes.replace(snap_instantiation.group(0), new_snap)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(routes)

update_routes('app/api/routes.py')
