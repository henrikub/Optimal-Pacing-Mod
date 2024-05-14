from flask import Flask, request
from flask_cors import CORS
import json
from optimal_pacing import *
from simulator import *

app = Flask(__name__)
CORS(app)

route_names = {
    'mech_isle_loop': 'Mech Isle Loop',
    'hilly_route': 'Hilly Route',
    'cobbled_climbs': 'Cobbled Climbs',
    'park_perimeter_loop': 'Park Perimeter Loop',
    'downtown_titans': 'Downtown Titans',
    'two_bridges_loop': 'Downtown Titans'
}

@app.route('/startbanner', methods=['POST'])
def write_json():
    data = request.get_json()
    print("Lead in", data)

    return 'Success', 200

@app.route('/runopt', methods=['POST'])
def run_opt():
    opt_config = request.get_json()
    print(opt_config)
    route_name = route_names[opt_config['route']]
    num_laps = opt_config['num_laps']
    routes_dict = {}
    with open('routes.json', 'r') as file:
        routes_dict = json.load(file)

    distance = routes_dict[route_name]['distance']
    elevation = routes_dict[route_name]['elevation']
    friction = routes_dict[route_name]['friction']
    lead_in = routes_dict[route_name]['lead_in']

    # Params
    params = {
        'mass_rider': opt_config['weight'],
        'mass_bike': 8.4,
        'g': 9.81,
        'mu': friction,
        'b0': 0.091,
        'b1': 0.0087,
        'Iw': 0.14,
        'r': 0.33,
        'Cd': 0.7,
        'rho': 1.2,
        # 'A': 0.0293*height**(0.725)*mass**(0.441) + 0.0604,
        'A': 0.4,
        'eta': 1,
        'w_prime': opt_config['w_prime'],
        'cp': opt_config['cp'],
        'alpha': (opt_config['max_power']-opt_config['cp'])/opt_config['w_prime']
        # 'alpha_c': 0.01,
        # 'c_max': 150,
        # 'c': 80
    }
    if num_laps != 1:
        new_elevation = []
        new_distance = []
        new_friction = []
        for i in range(num_laps):
            new_elevation.extend(elevation)
            new_friction.extend(friction)
            new_distance.extend([elem + i*max(distance) for elem in distance])
        elevation = new_elevation
        distance = new_distance
        friction = new_friction
        for i in range(len(distance)-10):
            if distance[i+1] - distance[i] < 0.6:
                distance.pop(i+1)
                elevation.pop(i+1)
                friction.pop(i+1)

    N = round(distance[-1]/5)
    timegrid = np.linspace(0,round(distance[-1]/1000*150), N)

    X, power, t_grid = create_initialization(timegrid, [distance[0], 1, params.get('w_prime')], distance, elevation, params)
    N = len(power)-1
    if opt_config['negative_split'] == False:
        w_bal_start = 0
        w_bal_end = 0
    else:
        w_bal_start = opt_config['bound_start']/100*opt_config['w_prime']
        w_bal_end = opt_config['bound_end']/100*opt_config['w_prime']

    optimization_opts = {
        "N": N,
        "time_initial_guess": t_grid[-1],
        "smooth_power_constraint": True,
        "w_bal_model": "ODE",
        "integration_method": opt_config['integration_method'],
        "solver": "ipopt",
        "negative_split": opt_config['negative_split'],
        "w_bal_start": w_bal_start,
        "w_bal_end": w_bal_end
    }
    
    initialization = {
        'pos_init': X[0],
        'speed_init': X[1],
        'w_bal_init': X[2],
        'power_init': power,
        'time_init': timegrid[-1],
    }
    sol, opti, T, U, X = solve_opt(distance, elevation, params, optimization_opts, initialization)
    t_grid = ca.linspace(0, sol.value(T), N+1)
    power_dict = {
        'power': sol.value(U).tolist(),
        'time': t_grid.full().flatten().tolist(),
        'distance': list(np.array(sol.value(X[0,:]).tolist())),
        'w_bal': sol.value(X[2,:]).tolist()
    }
    with open('pages/src/optimal_power.json', 'w') as file:
        json.dump(power_dict, file)
    return 'Success', 200


if __name__ == '__main__':
    app.run(port=5000)