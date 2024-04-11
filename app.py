import streamlit as st
from optimal_pacing import *
from optimization_plots import *
import casadi as ca
import numpy as np
from simulator import *
import json
import random
import sys
import websocket


request_id = f'random-req-id-{random.randint(1, 100000000)}'
sub_id = f'random-sub-id-{random.randint(1, 100000000)}'



st.title("Optimization settings")

cp = st.number_input('CP', value=265)
w_prime = st.number_input("W'", value=26630, min_value=1)
route_name = st.selectbox('Select route', ['Mech Isle Loop', 'Hilly Route', 'Downtown Titans', 'Richmond Rollercoaster', 'Greater London Flat', 'Cobbled Climbs', 'Canopies and Coastlines', 'Two Bridges Loop'])
num_laps = st.number_input('Number of Laps', value=1)
integration_method = st.selectbox('Select integration method', ['Euler', 'RK4', 'Midpoint'])


routes_dict = {}
with open('routes.json', 'r') as file:
    routes_dict = json.load(file)

distance = routes_dict[route_name]['distance']
elevation = routes_dict[route_name]['elevation']
# print(len(distance))
if num_laps != 1:
    new_elevation = []
    new_distance = []
    for i in range(num_laps):
        new_elevation.extend(elevation)
        new_distance.extend([elem + i*max(distance) for elem in distance])
    elevation = new_elevation
    distance = new_distance
    for i in range(len(distance)-10):
        if distance[i+1] - distance[i] < 0.6:
            distance.pop(i+1)
            elevation.pop(i+1)



# Params
params = {
    'mass_rider': 78,
    'mass_bike': 8,
    'g': 9.81,
    'mu': 0.004,
    'b0': 0.091,
    'b1': 0.0087,
    'Iw': 0.14,
    'r': 0.33,
    'Cd': 0.7,
    'rho': 1.2,
    'A': 0.4,
    'eta': 1,
    'w_prime': w_prime,
    'cp': cp,
    'alpha': 0.03,
    'alpha_c': 0.01,
    'c_max': 150,
    'c': 80
}

if st.button("Run optimization"):
    message = st.text("This could take several minutes..")
    N = round(distance[-1]/5)
    timegrid = np.linspace(0,round(distance[-1]/1000*150), N)

    X, power, t_grid = create_initialization(timegrid, [distance[0], 1, params.get('w_prime')], distance, elevation, params)
    N = len(power)-1
    optimization_opts = {
        "N": N,
        "time_initial_guess": t_grid[-1],
        "smooth_power_constraint": True,
        "w_bal_model": "ODE",
        "integration_method": integration_method,
        "solver": "ipopt"
    }
    
    initialization = {
        'pos_init': X[0],
        'speed_init': X[1],
        'w_bal_init': X[2],
        'power_init': power,
        'time_init': timegrid[-1],
    }
    sol, opti, T, U, X = solve_opt_warmstart_sim(distance, elevation, params, optimization_opts, initialization)
    stats = sol.stats()
    opt_details = {
        "N": N,
        "w_bal_model": optimization_opts.get("w_bal_model"),
        "integration_method": optimization_opts.get("integration_method"),
        "time_init_guess": optimization_opts.get("time_initial_guess"),
        "iterations": stats['iter_count'],
        "opt_time": stats['t_wall_total']
    }

    message.empty()

    fig2 = plot_optimization_results(sol, U, X, T, distance, elevation, params, opt_details, True)
    st.header("Optimization Results")
    st.pyplot(fig2)
    t_grid = ca.linspace(0, sol.value(T), N+1)
    power_dict = {
        'power': sol.value(U).tolist(),
        'time': t_grid.full().flatten().tolist(),
        'distance': sol.value(X[0,:]).tolist(),
        'w_bal': sol.value(X[2,:]).tolist()
    }
    with open('pages/src/optimal_power.json', 'w') as file:
        json.dump(power_dict, file)

placeholder = st.empty()
placeholder2 = st.empty()

def find_optimal_wbal(distance):
    opt_results = {}
    with open('pages/src/optimal_power.json', 'r') as file:
        opt_results = json.load(file)
    index = np.argwhere(np.array(opt_results['distance']) >= distance)[0][0]
    return opt_results['w_bal'][index]

def on_message(ws, raw_msg):
    msg = json.loads(raw_msg)
    if msg['type'] == 'response':
        if not msg['success']:
            raise Exception('subscribe request failure')
    elif msg['type'] == 'event' and msg['success']:
        data = msg['data']
        global athlete_state
        athlete_state = [data['state']['distance'], data['state']['speed']/3.6, data["stats"]["wBal"]]
        placeholder.text(f"Athlete state: {athlete_state}") 
        target_wbal = find_optimal_wbal(athlete_state[0])
        placeholder2.text(f"Optimal wbal:  {target_wbal}")
        if np.abs(athlete_state[2] - target_wbal) > 3000 and athlete_state[0] > 1000 and athlete_state[1] > 1: 
            # Reoptimize if w_bal is more than 5k off target, distance is longer than 1k and speed > 1mps
            print("Need to reoptimize!")
            index = np.argwhere(np.array(distance) > athlete_state[0])[0][0]
            dist = distance[index:]
            dist = [elem - distance[index] for elem in dist] # Shifting to start from 0
            elev = elevation[index:]
            N = round(dist[-1]/5)
            timegrid = np.linspace(0,round(dist[-1]/1000*150), N)
            try:
                sim_X, power, t_grid = create_initialization(timegrid, [dist[0], athlete_state[1], athlete_state[2]], dist, elev, params)
            except:
                print("something went wrong")

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
            athlete_state[0] = 0 # Optimize from 0
            try:
                reopt_sol, reopt_opti, reopt_T, reopt_U, reopt_X = reoptimize(dist, elev, athlete_state, params, optimization_opts, initialization)
            except:
                print("something went wrong")
            t_grid = ca.linspace(0, reopt_sol.value(reopt_T), N+1)
            pos = np.array(reopt_sol.value(reopt_X[0,:])) + distance[index] # Shift back to original
            dist = [elem + distance[index] for elem in dist]
            reopt_X[0,:] = pos
            power_dict = {
                'power': reopt_sol.value(reopt_U).tolist(),
                'time': t_grid.full().flatten().tolist(),
                'distance': reopt_sol.value(reopt_X[0,:]).tolist(),
                'w_bal': reopt_sol.value(reopt_X[2,:]).tolist()
            }
            with open('pages/src/optimal_power.json', 'w') as file:
                json.dump(power_dict, file)
            

def on_error(ws, error):
    print("socket error", error)


def on_close(ws, status_code, msg):
    print("socket closed", status_code, msg)


def on_open(ws):
    ws.send(json.dumps({
        "type": "request",
        "uid": request_id,
        "data": {
            "method": "subscribe",
            "arg": {
                "event": "athlete/watching", # watching, nearby, groups, etc...
                "subId": sub_id
            }
        }
    }))

def run_websocket():
        #websocket.enableTrace(True)
    if len(sys.argv) < 2:
        host = "ws://localhost:1080/api/ws/events"
    else:
        host = sys.argv[1]
    print("Connecting to:", host)
    ws = websocket.WebSocketApp(host,
                                on_open = on_open,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    ws.run_forever()

if st.button('Start Time Trial'):
    run_websocket()
    
    