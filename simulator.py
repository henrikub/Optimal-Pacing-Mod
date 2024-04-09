import casadi as ca
from scipy.ndimage import gaussian_filter1d
from optimal_pacing import calculate_gradient, smooth_w_balance_ode_derivative
import numpy as np

def create_initialization(time, x0, distance, elevation, params):
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

    #Physiological model params
    w_prime = params.get("w_prime")
    cp = params.get("cp")

    sigma = 4
    smoothed_elev = gaussian_filter1d(elevation, sigma)

    slope = calculate_gradient(distance, smoothed_elev)

    interpolated_slope = ca.interpolant('Slope', 'bspline', [distance], slope)
        
    def system_dynamics(x, u):
        return ca.vertcat(x[1], 
                (1/x[1] * 1/(m + Iw/r**2)) * (eta*u - mu*m*g*x[1] - m*g*interpolated_slope(x[0])*x[1] - b0*x[1] - b1*x[1]**2 - 0.5*Cd*rho*A*x[1]**3),
                smooth_w_balance_ode_derivative(u, cp, x, w_prime)) 

    tf = time[-1]
    N = len(time)
    t_grid = np.linspace(0,tf,N)


    dt = tf/N  
    x = ca.MX.sym('x', 3) 
    u = ca.MX.sym('u', 1)  
    f = system_dynamics(x, u)  
    ode = {'x': x, 'p': u, 'ode': f}  
    opts = {'tf': dt} 
    F = ca.integrator('F', 'rk', ode, opts)  

    done = False
    slope_const = 2500
    while not done:
        X = np.zeros((3, N))
        U = lambda pos: cp + slope_const*interpolated_slope(pos)
        power = []

        X[:,0] = x0
        for k in range(N-1):
            res = F(x0=X[:,k], p=U(X[0,k]))  
            X[:,k+1] = res['xf'].full().flatten()
            power.append(U(X[0,k]))  
        
        power = np.array(power).flatten()

        if (X[2] < 1000).any():
            slope_const -= 50
        else:
            done = True

        end_index = np.argwhere(np.array(X[0,:]) >= distance[-1])[0][0]
    print("Slope constant is ", slope_const)
    return X[:,:end_index], power[:end_index], t_grid[:end_index]