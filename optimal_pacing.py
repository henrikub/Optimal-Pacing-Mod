import casadi as ca
import numpy as np
from scipy.ndimage import gaussian_filter1d

def calculate_gradient(distance, elevation):
    gradient = []
    for i in range(len(distance)-1):
        delta_elevation = elevation[i] - elevation[i+1]
        delta_distance = distance[i] - distance[i+1]
        if delta_distance != 0:
            gradient.append(delta_elevation/delta_distance)
        else:
            gradient.append(0)
    gradient.append(0)
    return gradient

def extend_route(distance, elevation, friction, num_laps):
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
    return new_distance, new_elevation, new_friction

def smooth_w_balance_ode_derivative(u, cp, x, w_prime, smoothness=10):
    transition = 0.5 + 0.5*ca.tanh((u - cp)/smoothness)
    
    return (1-transition)*(1-x[2]/w_prime)*(cp-u) + transition*(cp-u)

def moving_avg(x, window_size):
    return np.convolve(x, np.ones(window_size), 'valid') / window_size

def normalized_power(power):
    ma = moving_avg(power, 30)
    ma_r = np.power(ma, 4)
    avg = np.mean(ma_r)
    return np.power(avg, 1/4)

def solve_opt(distance, elevation, params, optimization_opts, initialization):
    N = optimization_opts.get("N")
    opti = ca.Opti()
    X = opti.variable(3, N+1)
    pos = X[0,:]
    speed = X[1,:]
    w_bal = X[2,:]
    U = opti.variable(1,N+1)
    T = opti.variable()

    # Mechanical model params
    mass_rider = params.get("mass_rider")
    mass_bike = params.get("mass_bike")
    m = mass_bike + mass_rider
    g = params.get("g")
    mu = params.get("mu")
    b0 = params.get("b0")
    b1 = params.get("b1")
    Iw = params.get("Iw")
    r = params.get("r")
    Cd = params.get("Cd")
    rho = params.get("rho")
    A = params.get("A")
    eta = params.get("eta")

    # Physiological model params
    w_prime = params.get("w_prime")
    cp = params.get("cp")

    sigma = 2
    smoothed_elev = gaussian_filter1d(elevation, sigma)

    slope = calculate_gradient(distance, smoothed_elev)
    interpolated_slope = ca.interpolant('Slope', 'bspline', [distance], slope)
    interpolated_friction = ca.interpolant('Friction', 'bspline', [distance], mu)

    if optimization_opts.get("w_bal_model") == "ODE":  
        f = lambda x,u: ca.vertcat(x[1], 
                    (1/x[1] * 1/(m + Iw/r**2)) * (eta*u - interpolated_friction(x[0])*m*g*x[1] - m*g*interpolated_slope(x[0])*x[1] - b0*x[1] - b1*x[1]**2 - 0.5*Cd*rho*A*x[1]**3),
                    smooth_w_balance_ode_derivative(u, cp, x, w_prime))     
    elif optimization_opts.get("w_bal_model") == "Simple":
        f = lambda x,u: ca.vertcat(x[1], 
                    (1/x[1] * 1/(m + Iw/r**2)) * (eta*u - interpolated_friction(x[0])*m*g*x[1] - m*g*interpolated_slope(x[0])*x[1] - b0*x[1] - b1*x[1]**2 - 0.5*Cd*rho*A*x[1]**3), 
                    -(u-cp))
    else:
        raise ValueError()

    dt = T/N
    if optimization_opts.get("integration_method") == "Euler":
        for k in range(N):
            x_next = X[:,k] + dt*f(X[:,k], U[:,k])
            opti.subject_to(X[:,k+1] == x_next)
    elif optimization_opts.get("integration_method") == "Midpoint":
        for k in range(N):
            k1 = f(X[:,k], U[:,k])
            x_next = X[:,k] + dt*f(X[:,k] + dt/2*k1, U[:,k])
            opti.subject_to(X[:,k+1] == x_next)
    elif optimization_opts.get("integration_method") == "RK4":
        for k in range(N): 
            k1 = f(X[:,k], U[:,k])
            k2 = f(X[:,k] + dt/2*k1, U[:,k])
            k3 = f(X[:,k] + dt/2*k2, U[:,k])
            k4 = f(X[:,k] + dt*k3, U[:,k])
            x_next = X[:,k] + dt/6*(k1+2*k2+2*k3+k4)
            opti.subject_to(X[:,k+1] == x_next)
    else:
        raise ValueError()
    
    if optimization_opts.get("smooth_power_constraint"):
        opti.minimize(T + 0.00005 * ca.sumsqr(U[:,1:] - U[:,:-1])) 
    else:
        opti.minimize(T) 


    # Max power constraint params
    alpha = params.get("alpha")
    U_max = alpha*w_bal + cp

    # Set the path constraints
    opti.subject_to(U <= U_max)
    opti.subject_to(U >= 0)
    opti.subject_to(opti.bounded(0, w_bal, w_prime))
    opti.subject_to(opti.bounded(1, speed, 25))

    if optimization_opts.get('negative_split'):
        w_bal_start = optimization_opts.get("w_bal_start")
        w_bal_end = optimization_opts.get("w_bal_end")
        x = ca.linspace(0,T,N+1)
        opti.subject_to(w_bal > (w_bal_end-w_bal_start)/T *ca.transpose(x) + w_bal_start)

    # Set boundary conditions
    opti.subject_to(pos[0]==distance[0]) 
    opti.subject_to(speed[0]==1) 
    opti.subject_to(pos[-1]==distance[-1])
    opti.subject_to(w_bal[0]==w_prime)

    opti.subject_to(opti.bounded(0, T, distance[-1]/1000*180)) 

    # Provide an initial guess
    opti.set_initial(T, initialization.get('time_init'))
    opti.set_initial(pos, initialization.get('pos_init'))
    opti.set_initial(speed, initialization.get('speed_init'))
    opti.set_initial(w_bal, initialization.get('w_bal_init'))
    opti.set_initial(U, initialization.get('power_init'))

    p_opts = {"expand": False}
    s_opts = {"max_iter": 20000}
    opti.solver(optimization_opts.get('solver'), p_opts, s_opts) 
    sol = opti.solve()
    return sol, opti, T, U, X


def reoptimize(distance, elevation, X0, params, optimization_opts, initialization):
    N = optimization_opts.get("N")
    opti = ca.Opti()
    X = opti.variable(3, N+1)
    pos = X[0,:]
    speed = X[1,:]
    w_bal = X[2,:]
    U = opti.variable(1,N+1)
    T = opti.variable()

    # Mechanical model params
    mass_rider = params.get("mass_rider")
    mass_bike = params.get("mass_bike")
    m = mass_bike + mass_rider
    g = params.get("g")
    mu = params.get("mu")
    b0 = params.get("b0")
    b1 = params.get("b1")
    Iw = params.get("Iw")
    r = params.get("r")
    Cd = params.get("Cd")
    rho = params.get("rho")
    A = params.get("A")
    eta = params.get("eta")

    # Physiological model params
    w_prime = params.get("w_prime")
    cp = params.get("cp")

    sigma = 4
    smoothed_elev = gaussian_filter1d(elevation, sigma)

    slope = calculate_gradient(distance, smoothed_elev)
    interpolated_slope = ca.interpolant('Slope', 'bspline', [distance], slope)
    interpolated_friction = ca.interpolant('Friction', 'bspline', [distance], mu)

    if optimization_opts.get("w_bal_model") == "ODE":  
        f = lambda x,u: ca.vertcat(x[1], 
                    (1/x[1] * 1/(m + Iw/r**2)) * (eta*u - interpolated_friction(x[0])*m*g*x[1] - m*g*interpolated_slope(x[0])*x[1] - b0*x[1] - b1*x[1]**2 - 0.5*Cd*rho*A*x[1]**3),
                    smooth_w_balance_ode_derivative(u, cp, x, w_prime))     
    elif optimization_opts.get("w_bal_model") == "Simple":
        f = lambda x,u: ca.vertcat(x[1], 
                    (1/x[1] * 1/(m + Iw/r**2)) * (eta*u - interpolated_friction(x[0])*m*g*x[1] - m*g*interpolated_slope(x[0])*x[1] - b0*x[1] - b1*x[1]**2 - 0.5*Cd*rho*A*x[1]**3), 
                    -(u-cp))
    else:
        raise ValueError()

    dt = T/N
    if optimization_opts.get("integration_method") == "Euler":
        for k in range(N):
            x_next = X[:,k] + dt*f(X[:,k], U[:,k])
            opti.subject_to(X[:,k+1] == x_next)
    elif optimization_opts.get("integration_method") == "Midpoint":
        for k in range(N):
            k1 = f(X[:,k], U[:,k])
            x_next = X[:,k] + dt*f(X[:,k] + dt/2*k1, U[:,k])
            opti.subject_to(X[:,k+1] == x_next)
    elif optimization_opts.get("integration_method") == "RK4":
        for k in range(N): 
            k1 = f(X[:,k], U[:,k])
            k2 = f(X[:,k] + dt/2*k1, U[:,k])
            k3 = f(X[:,k] + dt/2*k2, U[:,k])
            k4 = f(X[:,k] + dt*k3, U[:,k])
            x_next = X[:,k] + dt/6*(k1+2*k2+2*k3+k4)
            opti.subject_to(X[:,k+1] == x_next)
    else:
        raise ValueError()
    
    if optimization_opts.get("smooth_power_constraint"):
        opti.minimize(T + 0.00005 * ca.sumsqr(U[:,1:] - U[:,:-1])) 
    else:
        opti.minimize(T) 


    # Max power constraint params
    alpha = params.get("alpha")
    U_max = alpha*w_bal + cp

    # Set the path constraints
    opti.subject_to(U <= U_max)
    opti.subject_to(U >= 0)
    opti.subject_to(opti.bounded(0, w_bal, w_prime))
    opti.subject_to(opti.bounded(1, speed, 25))

    # Set boundary conditions
    opti.subject_to(pos[0]==X0[0]) 
    opti.subject_to(speed[0]==X0[1]) 
    opti.subject_to(pos[-1]==distance[-1])
    opti.subject_to(w_bal[0]==X0[2])

    opti.subject_to(opti.bounded(0, T, distance[-1]/1000*180)) 

    # Provide an initial guess
    opti.set_initial(T, initialization.get('time_init'))
    opti.set_initial(pos, initialization.get('pos_init'))
    opti.set_initial(speed, initialization.get('speed_init'))
    opti.set_initial(w_bal, initialization.get('w_bal_init'))
    opti.set_initial(U, initialization.get('power_init'))
 
    p_opts = {"expand": False}
    s_opts = {"max_iter": 20000}
    opti.solver(optimization_opts.get('solver'), p_opts, s_opts) 
    sol = opti.solve()
    return sol, opti, T, U, X