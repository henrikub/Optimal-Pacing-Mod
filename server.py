from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import optimal_pacing as opt
from simulator import *
from optimization_plots import *

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

@app.route('/runopt', methods=['POST'])
def run_opt():
    opt_config = request.get_json()
    route_name = route_names[opt_config['route']]
    num_laps = opt_config['num_laps']
    routes_dict = {}
    with open('routes.json', 'r') as file:
        routes_dict = json.load(file)

    distance = routes_dict[route_name]['distance']
    elevation = routes_dict[route_name]['elevation']
    friction = routes_dict[route_name]['friction']
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
    sol, opti, T, U, X = opt.solve_opt(distance, elevation, params, optimization_opts, initialization)
    stats = sol.stats()
    opt_details = {
        "N": N,
        "w_bal_model": optimization_opts.get("w_bal_model"),
        "integration_method": optimization_opts.get("integration_method"),
        "time_init_guess": optimization_opts.get("time_initial_guess"),
        "iterations": stats['iter_count'],
        "opt_time": stats['t_wall_total'],
        "negative_split": optimization_opts.get("negative_split"),
        "w_bal_start": optimization_opts.get("w_bal_start"),
        "w_bal_end": optimization_opts.get("w_bal_end")
    }

    fig2 = plot_optimization_results(sol, U, X, T, distance, elevation, params, opt_details, False)
    t_grid = ca.linspace(0, sol.value(T), N+1)
    power_dict = {
        'power': sol.value(U).tolist(),
        'time': t_grid.full().flatten().tolist(),
        'distance': list(np.array(sol.value(X[0,:]).tolist())),
        'w_bal': sol.value(X[2,:]).tolist()
    }
    with open('pages/src/optimal_power.json', 'w') as file:
        json.dump(power_dict, file)
    return jsonify({'result': 'Success'}), 200


@app.route('/reoptimization', methods=['POST'])
def reoptimize():
    opt_config = request.get_json()
    initial_state = [opt_config['distance'], opt_config['speed'], opt_config['w_bal']]
    route_name = route_names[opt_config['route']]
    num_laps = opt_config['num_laps']
    routes_dict = {}

    with open('routes.json', 'r') as file:
        routes_dict = json.load(file)

    distance = routes_dict[route_name]['distance']
    elevation = routes_dict[route_name]['elevation']
    friction = routes_dict[route_name]['friction']
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


    index = np.argwhere(np.array(distance) > initial_state[0])[0][0]
    dist = distance[index:]
    dist = [elem - distance[index] for elem in dist] # Shifting to start from 0
    elev = elevation[index:]
    params['mu'] = friction[index:]
    N = round(dist[-1]/5)
    timegrid = np.linspace(0,round(dist[-1]/1000*150), N)

    try:
        sim_X, power, t_grid = create_initialization(timegrid, [dist[0], initial_state[1], initial_state[2]], dist, elev, params)
    except:
        print("Something went wrong")

    N = len(power)-1
    optimization_opts = {
        "N": N,
        "time_initial_guess": t_grid[-1],
        "smooth_power_constraint": True,
        "w_bal_model": "ODE",
        "integration_method": "Euler",
        "solver": "ipopt"
    }
    initialization = {
        'pos_init': sim_X[0],
        'speed_init': sim_X[1],
        'w_bal_init': sim_X[2],
        'power_init': power,
        'time_init': t_grid[-1],
    }            
    
    try:
        reopt_sol, reopt_opti, reopt_T, reopt_U, reopt_X = opt.reoptimize(dist, elev, [0, initial_state[1], initial_state[2]], params, optimization_opts, initialization)
    except:
        print("something went wrong")
    t_grid = ca.linspace(0, reopt_sol.value(reopt_T), N+1)
    pos = np.array(reopt_sol.value(reopt_X[0,:])) + distance[index] # Shift back to original
    power_dict = {
        'power': reopt_sol.value(reopt_U).tolist(),
        'time': t_grid.full().flatten().tolist(),
        'distance': pos.tolist(),
        'w_bal': reopt_sol.value(reopt_X[2,:]).tolist()
    }
    with open('pages/src/optimal_power.json', 'w') as file:
        json.dump(power_dict, file)

    return jsonify({'result': 'Success'}), 200


if __name__ == '__main__':
    app.run(port=5000)