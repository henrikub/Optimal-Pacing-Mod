import casadi as ca
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


def smooth_w_balance_ode_derivative(u, cp, x, w_prime, smooth_factor=0.1):
    transition = ca.tanh(smooth_factor * (u - cp))
    transition = 0.5 * (transition + 1)
    
    return transition * (-(u - cp)) + (1 - transition) * ((1 - x[2]/w_prime)*(cp - u))

def solve_opt_warmstart_sim(distance, elevation, params, optimization_opts, initialization):
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

    if optimization_opts.get("w_bal_model") == "ODE":  
        f = lambda x,u: ca.vertcat(x[1], 
                    (1/x[1] * 1/(m + Iw/r**2)) * (eta*u - mu*m*g*x[1] - m*g*interpolated_slope(x[0])*x[1] - b0*x[1] - b1*x[1]**2 - 0.5*Cd*rho*A*x[1]**3),
                    smooth_w_balance_ode_derivative(u, cp, x, w_prime))     
    elif optimization_opts.get("w_bal_model") == "Simple":
        f = lambda x,u: ca.vertcat(x[1], 
                    (1/x[1] * 1/(m + Iw/r**2)) * (eta*u - mu*m*g*x[1] - m*g*interpolated_slope(x[0])*x[1] - b0*x[1] - b1*x[1]**2 - 0.5*Cd*rho*A*x[1]**3), 
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
    alpha_c = params.get("alpha_c")
    c_max = params.get("c_max")
    c = params.get("c")
    U_max = 4*(alpha*w_bal + cp)*(c/(alpha_c*w_bal + c_max)*(1-c/(alpha_c*w_bal + c_max)))

    # Set the path constraints
    opti.subject_to(U <= U_max)
    opti.subject_to(U >= 0)
    opti.subject_to(opti.bounded(0, w_bal, w_prime))
    opti.subject_to(opti.bounded(1, speed, 25))

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

    if optimization_opts.get("w_bal_model") == "ODE":  
        f = lambda x,u: ca.vertcat(x[1], 
                    (1/x[1] * 1/(m + Iw/r**2)) * (eta*u - mu*m*g*x[1] - m*g*interpolated_slope(x[0])*x[1] - b0*x[1] - b1*x[1]**2 - 0.5*Cd*rho*A*x[1]**3),
                    smooth_w_balance_ode_derivative(u, cp, x, w_prime))     
    elif optimization_opts.get("w_bal_model") == "Simple":
        f = lambda x,u: ca.vertcat(x[1], 
                    (1/x[1] * 1/(m + Iw/r**2)) * (eta*u - mu*m*g*x[1] - m*g*interpolated_slope(x[0])*x[1] - b0*x[1] - b1*x[1]**2 - 0.5*Cd*rho*A*x[1]**3), 
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
    alpha_c = params.get("alpha_c")
    c_max = params.get("c_max")
    c = params.get("c")
    U_max = 4*(alpha*w_bal + cp)*(c/(alpha_c*w_bal + c_max)*(1-c/(alpha_c*w_bal + c_max)))

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