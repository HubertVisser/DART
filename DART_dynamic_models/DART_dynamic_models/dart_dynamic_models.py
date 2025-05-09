import os
import glob
import pandas as pd
import numpy as np
from matplotlib import pyplot as plt
from colorama import Fore, Style, Back

def directly_measured_model_parameters():
    # from vicon system measurements
    theta_correction = 0.00768628716468811 # error between vehicle axis and vicon system reference axis
    lr_reference = 0.115  #0.11650    # (measureing it wit a tape measure it's 0.1150) reference point location taken by the vicon system measured from the rear wheel
    l_lateral_shift_reference = -0.01 # the reference point is shifted laterally by this amount 
    #COM_positon = 0.084 #0.09375 #centre of mass position measured from the rear wheel

    # car parameters
    l = 0.1735 # [m]length of the car (from wheel to wheel)
    m = 1.580 # mass [kg]
    m_front_wheel = 0.847 #[kg] mass pushing down on the front wheel
    m_rear_wheel = 0.733 #[kg] mass pushing down on the rear wheel


    COM_positon = l / (1+m_rear_wheel/m_front_wheel)
    lr = COM_positon
    lf = l-lr
    # Automatically adjust following parameters according to tweaked values
    l_COM = lr_reference - COM_positon

    #lateral measurements
    l_width = 0.08 # width of the car is 8 cm
    m_left_wheels = 0.794 # mass pushing down on the left wheels
    m_right_wheels = 0.805 # mass pushing down on the right wheels
    # so ok the centre of mass is pretty much in the middle of the car so won't add this to the derivations


    Jz = 1/12 * m *(l**2+l_width**2) #0.006513 # Moment of inertia of uniform rectangle of shape 0.1735 x 0.8 NOTE this is an approximation cause the mass is not uniformly distributed


    return [theta_correction, l_COM, l_lateral_shift_reference ,lr, lf, Jz, m,m_front_wheel,m_rear_wheel]


def model_parameters():
    # collect fitted model parameters here so that they can be easily accessed

    # full velocity range
    # motor parameters
    a_m =  25.35849952697754
    b_m =  4.815326690673828
    c_m =  -0.16377617418766022
    time_C_m =  0.0843319296836853
    # friction parameters
    a_f =  1.2659882307052612
    b_f =  7.666370391845703
    c_f =  0.7393041849136353
    d_f =  -0.11231517791748047

    # steering angle curve --from fitting on vicon data
    a_s =  1.392930030822754
    b_s =  0.36576229333877563
    c_s =  0.0029959678649902344 - 0.03 # littel adjustment to allign the tire curves
    d_s =  0.5147881507873535
    e_s =  1.0230425596237183


    # Front wheel parameters:
    d_t_f =  -0.8406859636306763
    c_t_f =  0.8407371044158936
    b_t_f =  8.598039627075195
    # Rear wheel parameters:
    d_t_r =  -0.8546739816665649
    c_t_r =  0.959108829498291
    b_t_r =  11.54928207397461


    #additional friction due to steering angle
    # Friction due to steering parameters:
    a_stfr =  -0.11826395988464355
    b_stfr =  5.915864944458008
    d_stfr =  0.22619032859802246
    e_stfr =  0.7793111801147461

    # steering dynamics
    k_stdn =  0.12851488590240479

    # pitch dynamics
    k_pitch =  0.14062348008155823
    w_natural_Hz_pitch =  2.7244157791137695



    return [a_m, b_m, c_m, time_C_m,
            a_f, b_f, c_f, d_f,
            a_s, b_s, c_s, d_s, e_s,
            d_t_f, c_t_f, b_t_f,d_t_r, c_t_r, b_t_r,
            a_stfr, b_stfr,d_stfr,e_stfr,
            k_stdn,
            k_pitch,w_natural_Hz_pitch]



class model_functions():
    # load model parameters
    [theta_correction_self, l_COM_self, l_lateral_shift_reference_self ,
     lr_self, lf_self, Jz_self, m_self,m_front_wheel_self,m_rear_wheel_self] = directly_measured_model_parameters()

    [a_m_self, b_m_self, c_m_self, d_m_self,
    a_f_self, b_f_self, c_f_self, d_f_self,
    a_s_self, b_s_self, c_s_self, d_s_self, e_s_self,
    d_t_f_self, c_t_f_self, b_t_f_self,d_t_r_self, c_t_r_self, b_t_r_self,
    a_stfr_self, b_stfr_self,d_stfr_self,e_stfr_self,
    k_stdn_self,k_pitch_self,w_natural_Hz_pitch_self] = model_parameters()

    def __init__(self):
        # this is just a class to collect all the functions that are used to model the dynamics
        pass

    def minmax_scale_hm(self,min,max,normalized_value):
        # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)

    def steering_2_steering_angle(self, steering_command, a_s, b_s, c_s, d_s, e_s):
        w_s = 0.5 * (np.tanh(30 * (steering_command + c_s)) + 1)
        steering_angle1 = b_s * np.tanh(a_s * (steering_command + c_s))
        steering_angle2 = d_s * np.tanh(e_s * (steering_command + c_s))
        steering_angle = (w_s) * steering_angle1 + (1 - w_s) * steering_angle2
        return steering_angle

    def rolling_friction(self, vx, a_f, b_f, c_f, d_f):
        F_rolling = - (a_f * np.tanh(b_f * vx) + c_f * vx + d_f * vx**2)
        return F_rolling

    def motor_force(self, throttle_filtered, v, a_m, b_m, c_m):
        w_m = 0.5 * (np.tanh(100 * (throttle_filtered + c_m)) + 1)
        Fx = (a_m - b_m * v) * w_m * (throttle_filtered + c_m)
        return Fx

    def evaluate_slip_angles(self, vx, vy, w, lf, lr, steer_angle):
        vy_wheel_f, vy_wheel_r = self.evalaute_wheel_lateral_velocities(vx, vy, w, steer_angle, lf, lr)
        vx_wheel_f = np.cos(-steer_angle) * vx - np.sin(-steer_angle) * (vy + lf * w)

        Vx_correction_term_f = 1 * np.exp(-3 * vx_wheel_f**2)
        Vx_correction_term_r = 1 * np.exp(-3 * vx**2)

        Vx_f = vx_wheel_f + Vx_correction_term_f
        Vx_r = vx + Vx_correction_term_r

        alpha_f = np.arctan2(vy_wheel_f, Vx_f)
        alpha_r = np.arctan2(vy_wheel_r, Vx_r)

        return alpha_f, alpha_r

    def lateral_forces_activation_term(self, vx):
        return np.tanh(100 * vx**2)

    def lateral_tire_force(self, alpha, d_t, c_t, b_t, m_wheel):
        F_y = m_wheel * 9.81 * d_t * np.sin(c_t * np.arctan(b_t * alpha))
        return F_y

    def evalaute_wheel_lateral_velocities(self, vx, vy, w, steer_angle, lf, lr):
        Vy_wheel_f = - np.sin(steer_angle) * vx + np.cos(steer_angle) * (vy + lf * w)
        Vy_wheel_r = vy - lr * w
        return Vy_wheel_f, Vy_wheel_r

    def F_friction_due_to_steering(self, steer_angle, vx, a, b, d, e):
        friction_term = a + (b * steer_angle * np.tanh(30 * steer_angle))
        vx_term = - (0.5 + 0.5 * np.tanh(20 * (vx - 0.3))) * (e + d * (vx - 0.5))
        return vx_term * friction_term

    def solve_rigid_body_dynamics(self, vx, vy, w, steer_angle, Fx_front, Fx_rear, Fy_wheel_f, Fy_wheel_r, lf, lr, m, Jz):
        a_cent_x = w * vy
        a_cent_y = -w * vx

        Fx_body = Fx_front * np.cos(steer_angle) + Fx_rear + Fy_wheel_f * -np.sin(steer_angle)
        Fy_body = Fx_front * np.sin(steer_angle) + Fy_wheel_f * np.cos(steer_angle) + Fy_wheel_r

        M = Fx_front * np.sin(steer_angle) * lf + Fy_wheel_f * np.cos(steer_angle) * lf + Fy_wheel_r * -lr

        acc_x = Fx_body / m + a_cent_x
        acc_y = Fy_body / m + a_cent_y
        acc_w = M / Jz

        return acc_x, acc_y, acc_w
    

        
    def critically_damped_2nd_order_dynamics_numpy(self,x_dot,x,forcing_term,w_Hz):
        z = 1 # critically damped system
        w_natural = w_Hz * 2 * np.pi # convert to rad/s
        x_dot_dot = w_natural ** 2 * (forcing_term - x) - 2* w_natural * z * x_dot
        return x_dot_dot


    def produce_past_action_coefficients_1st_oder(self,C,length,dt):
        
        k_vec = np.zeros((length,1))
        for i in range(length):
            k_vec[i] = self.impulse_response_1st_oder(i*dt,C) 
        k_vec = k_vec * dt # the dt is really important to get the amplitude right
        return k_vec 


    def impulse_response_1st_oder(self,t,C):
        return np.exp(-t/C)*1/C



    def produce_past_action_coefficients_1st_oder_step_response(self,C,length,dt):
            
        k_vec = np.zeros((length,1))
        for i in range(1,length): # the first value is zero because it has not had time to act yet
            k_vec[i] = self.step_response_1st_oder(i*dt,C) - self.step_response_1st_oder((i-1)*dt,C)  
            
        return k_vec 
    

    def step_response_1st_oder(self,t,C):
        return 1 - np.exp(-t/C)
        
    def continuous_time_1st_order_dynamics(self,x,forcing_term,C):
        x_dot = 1/C * (forcing_term - x)
        return x_dot





def get_data(folder_path):
    import csv
    import os

    # This function gets (or produces) the merged data files from the specified folder
    print('Getting data')
    print('Looking for file " merged_files.csv "  in folder "', folder_path,'"')

    file_name = 'merged_files.csv'
    # Check if the CSV file exists in the folder
    file_path = os.path.join(folder_path, file_name)

    if os.path.exists(file_path) and os.path.isfile(file_path):
        print('The CSV file exists in the specified folder.')

    else:
        print('The CSV file does not already exist in the specified folder. Proceding with file generation.')
        merge_data_files_from_a_folder(folder_path)

    #recording_name_train = file_name
    df = pd.read_csv(file_path)
    print('Raw data succesfully loaded.')
    return df



# def merge_data_files_from_a_folder(folder_path):
    #this method creates a single file from all .csv files in the specified folder

    # Output file name and path
    file_name = 'merged_files.csv'
    output_file_path = folder_path + '/' + file_name

    # Get all CSV file paths in the folder
    csv_files = glob.glob(os.path.join(folder_path, '*.csv'))
    csv_files.sort(key=lambda x: os.path.basename(x))

    dataframes = []
    timing_offset = 0

    # Read each CSV file and store it in the dataframes list
    for csv_file in csv_files:
        df = pd.read_csv(csv_file)

        #sometimes the files have some initial lines where all values are zero, so just remove them
        df = df[df['elapsed time sensors'] != 0.0]

        # set throttle to 0 when safety is off
        df['throttle'][df['safety_value'] == 0.0] = 0.0

        # reset time in each file to start from zero
        df['elapsed time sensors'] -= df['elapsed time sensors'].iloc[0]
        df['elapsed time sensors'] += timing_offset

        

        if 'vicon time' in df.keys():
            df['vicon time'] -= df['vicon time'].iloc[0]
            df['vicon time'] += timing_offset
            dt = np.average(df['vicon time'].diff().to_numpy()[1:]) # evaluate dt
            timing_offset = df['vicon time'].iloc[-1] + dt 
            # stitch position together so to avoid instantaneous change of position
            if dataframes:
                df['vicon x'] = df['vicon x'] - df['vicon x'].iloc[0]
                df['vicon y'] = df['vicon y'] - df['vicon y'].iloc[0]

                # now x and y must be rotated to allign with the previous file's last orientation
                theta = dataframes[-1]['vicon yaw'].iloc[-1] - df['vicon yaw'].iloc[0]
                # Compute the new x and y coordinates after rotation
                rotated_x = df['vicon x'].to_numpy() * np.cos(theta) - df['vicon y'].to_numpy() * np.sin(theta)
                rotated_y = df['vicon x'].to_numpy() * np.sin(theta) + df['vicon y'].to_numpy() * np.cos(theta)

                # this matches up the translation
                df['vicon x'] = rotated_x + dataframes[-1]['vicon x'].iloc[-1]
                df['vicon y'] = rotated_y + dataframes[-1]['vicon y'].iloc[-1]

                #not stich together the rotation angle
                df['vicon yaw'] = df['vicon yaw'] + theta #- df['vicon yaw'].iloc[0] + dataframes[-1]['vicon yaw'].iloc[-1]
                # correct yaw that may now be less than pi
                #df['vicon yaw'] = (df['vicon yaw'] + np.pi) % (2 * np.pi) - np.pi
        else:
            #update timing offset
            #extract safety off data and fix issues with timing
            dt = np.average(df['elapsed time sensors'].diff().to_numpy()[1:]) # evaluate dt
            timing_offset = df['elapsed time sensors'].iloc[-1] + dt # each file will have a dt timegap between it and the next file
        


        
        dataframes.append(df)

    # Concatenate all DataFrames into a single DataFrame vertically
    merged_df = pd.concat(dataframes, axis=0, ignore_index=True)

    #write merged csv file
    merged_df.to_csv(output_file_path, index=False)

    print('Merging complete. Merged file saved as:', output_file_path)
    return output_file_path #, num_lines



def evaluate_delay(signal1,signal2):
    # outputs delay expressed in vector index jumps
    # we assume that the signals are arrays of the same length
    if len(signal1) == len(signal2):
    
        # Use numpy's correlate function to find cross-correlation
        cross_corr = np.correlate(signal1, signal2, mode='full')
        #the length of the cross_corr vector will be N + N - 1
        # in position N you find the cross correlation for 0 delay
        # signal 1 is kept still and signal 2 is moved across. 
        # So if signal 2 is a delayed version of signal 1, the maximum
        # value of the cross correlation will accur before position N. (N means no delay)

        # Find the index of the maximum correlation
        delay_indexes = (len(signal1)) - (np.argmax(cross_corr)+1)  # plus one is needed cause np.argmax gives you the index of where that is

        return delay_indexes
    else:
        print('signals not of the same length! Stopping delay evaluation')


def process_raw_data_steering(df):
    
    # evaluate measured steering angle by doing inverse of kinematic bicycle model (only when velocity is higher than 0.8 m/s)
    # Note that dataset should not contain high velocities since the kinematic bicycle model will fail, and measured steering angle would be wrong
    L = 0.175 # distance between front and rear axels
    elapsed_time_vec = df['elapsed time sensors'][df['vel encoder'] > 0.8].to_numpy()
    #steering_delayed = df['steering delayed'][df['vel encoder'] > 0.8].to_numpy()
    steering = df['steering'][df['vel encoder'] > 0.8].to_numpy()

    vel_encoder = df['vel encoder'][df['vel encoder'] > 0.8].to_numpy()
    w_vec = df['W (IMU)'][df['vel encoder'] > 0.8].to_numpy()
    steering_angle= np.arctan2(w_vec * L ,  vel_encoder) 

    d = {'elapsed time sensors': elapsed_time_vec,
        #'W (IMU)': w_vec,
        'steering angle': steering_angle,
        #'steering delayed' : steering_delayed,
        'steering' : steering}

    df_steering_angle = pd.DataFrame(data=d)

    return df_steering_angle



def throttle_dynamics_data_processing(df_raw_data):
    mf = model_functions() # instantiate the model functions object

    dt = df_raw_data['vicon time'].diff().mean()  # Calculate the average time step
    th = 0
    filtered_throttle = np.zeros(df_raw_data.shape[0])
    # Loop through the data to compute the predicted steering angles

    ground_truth_refinement = 100 # this is used to integrate the steering angle with a higher resolution to avoid numerical errors
    for t in range(1, len(filtered_throttle)):
        # integrate ground trough with a much higher dt to have better numerical accuracy
        for k in range(ground_truth_refinement):
            th_dot = mf.continuous_time_1st_order_dynamics(th,df_raw_data['throttle'].iloc[t-1],mf.d_m_self)
            th += dt/ground_truth_refinement * th_dot
        filtered_throttle[t] = th

    return filtered_throttle


def steering_dynamics_data_processing(df_raw_data):
    mf = model_functions() # instantiate the model functions object

    # -------------------  forard integrate the steering signal  -------------------
    dt = df_raw_data['vicon time'].diff().mean()  # Calculate the average time step

    #steering = df_raw_data['steering'].to_numpy()

    # Initialize variables for the steering prediction
    st = 0
    st_vec = np.zeros(df_raw_data.shape[0])
    st_vec_angle_vec = np.zeros(df_raw_data.shape[0])

    # Loop through the data to compute the predicted steering angles
    for t in range(1, df_raw_data.shape[0]):
        ground_truth_refinement = 100 # this is used to integrate the steering angle with a higher resolution to avoid numerical errors
        for k in range(ground_truth_refinement):
            st_dot = mf.continuous_time_1st_order_dynamics(st,df_raw_data['steering'].iloc[t-1],mf.k_stdn_self) 
            # Update the steering value with the time step
            st += st_dot * dt/ground_truth_refinement

        # Compute the steering angle using the two models with weights
        steering_angle = mf.steering_2_steering_angle(st, mf.a_s_self,
                                                          mf.b_s_self,
                                                          mf.c_s_self,
                                                          mf.d_s_self,
                                                          mf.e_s_self)

        # Store the predicted steering angle
        st_vec_angle_vec[t] = steering_angle
        st_vec[t] = st

    return st_vec_angle_vec, st_vec



def plot_raw_data(df):
    plotting_time_vec = df['elapsed time sensors'].to_numpy()

    fig1, ((ax0, ax1, ax2)) = plt.subplots(3, 1, figsize=(10, 6), constrained_layout=True)
    ax0.set_title('dt check')
    ax0.plot(np.diff(df['elapsed time sensors']), label="dt", color='gray')
    ax0.set_ylabel('dt [s]')
    ax0.set_xlabel('data point')
    ax0.legend()

    # plot raw data velocity vs throttle
    ax1.set_title('Raw Velocity vs throttle')
    ax1.plot(plotting_time_vec, df['vel encoder'].to_numpy(), label="V encoder [m/s]", color='dodgerblue')
    ax1.plot(plotting_time_vec, df['throttle'].to_numpy(), label="throttle raw []", color='gray')
    # Create a background where the safety is disingaged
    mask = np.array(df['safety_value']) == 1
    ax1.fill_between(plotting_time_vec, ax1.get_ylim()[0], ax1.get_ylim()[1], where=mask, color='gray', alpha=0.1, label='safety value disingaged')
    ax1.set_xlabel('time [s]')
    ax1.legend()

    # plot raw data w vs steering
    ax2.set_title('Raw Omega')
    ax2.plot(plotting_time_vec, df['W (IMU)'].to_numpy(),label="omega IMU raw data [rad/s]", color='orchid')
    ax2.plot(plotting_time_vec, df['steering'].to_numpy(),label="steering raw []", color='pink') 
    ax2.fill_between(plotting_time_vec, ax2.get_ylim()[0], ax2.get_ylim()[1], where=mask, color='gray', alpha=0.1, label='safety value disingaged')
    ax2.set_xlabel('time [s]')
    ax2.legend()
    return ax0,ax1,ax2


def process_vicon_data_kinematics(df,steps_shift):
    print('Processing kinematics data')
    mf = model_functions()

    # resampling the robot data to have the same time as the vicon data
    from scipy.interpolate import interp1d

    # Step 1: Identify sensor time differences and extract sensor checkpoints
    sensor_time_diff = df['elapsed time sensors'].diff()

    # Times where sensor values change more than 0.01s (100Hz -> 10Hz)
    sensor_time = df['elapsed time sensors'][sensor_time_diff > 0.01].to_numpy()
    steering_at_checkpoints = df['steering'][sensor_time_diff > 0.01].to_numpy()

    # Step 2: Interpolate using Zero-Order Hold
    zoh_interp = interp1d(sensor_time, steering_at_checkpoints, kind='previous', bounds_error=False, fill_value="extrapolate")

    # Step 3: Apply interpolation to 'vicon time'
    df['steering'] = zoh_interp(df['vicon time'].to_numpy())

    
    robot2vicon_delay = 0 # samples delay between the robot and the vicon data # very important to get it right (you can see the robot reacting to throttle and steering inputs before they have happened otherwise)
    # this is beacause the lag between vicon-->laptop, and robot-->laptop is different. (The vicon data arrives sooner)

    # there is a timedelay between robot and vicon system. Ideally the right way to do this would be to shift BACKWARDS in time the robot data.
    # but equivalently we can shift FORWARDS in time the vicon data. This is done by shifting the vicon time backwards by the delay time.
    # This is ok since we just need the data to be consistent. but be aware of this
    df['vicon x'] = df['vicon x'].shift(+robot2vicon_delay)
    df['vicon y'] = df['vicon y'].shift(+robot2vicon_delay)
    df['vicon yaw'] = df['vicon yaw'].shift(+robot2vicon_delay)
    # account for fisrt values that will be NaN
    df['vicon x'].iloc[:robot2vicon_delay] = df['vicon x'].iloc[robot2vicon_delay]
    df['vicon y'].iloc[:robot2vicon_delay] = df['vicon y'].iloc[robot2vicon_delay]
    df['vicon yaw'].iloc[:robot2vicon_delay] = df['vicon yaw'].iloc[robot2vicon_delay]


    #  ---  relocating reference point to the centre of mass  ---
    df['vicon x'] = df['vicon x'] - mf.l_COM_self*np.cos(df['vicon yaw']) - mf.l_lateral_shift_reference_self*np.cos(df['vicon yaw']+np.pi/2)
    df['vicon y'] = df['vicon y'] - mf.l_COM_self*np.sin(df['vicon yaw']) - mf.l_lateral_shift_reference_self*np.sin(df['vicon yaw']+np.pi/2)
    # -----------------------------------------------------------


    # -----     KINEMATICS      ------
    df['unwrapped yaw'] = unwrap_hm(df['vicon yaw'].to_numpy()) + mf.theta_correction_self


    # --- evaluate first time derivative ---

    shifted_time0 = df['vicon time'].shift(+steps_shift)
    shifted_x0 = df['vicon x'].shift(+steps_shift)
    shifted_y0 = df['vicon y'].shift(+steps_shift)
    shifted_yaw0 = df['unwrapped yaw'].shift(+steps_shift)

    shifted_time2 = df['vicon time'].shift(-steps_shift)
    shifted_x2 = df['vicon x'].shift(-steps_shift)
    shifted_y2 = df['vicon y'].shift(-steps_shift)
    shifted_yaw2 = df['unwrapped yaw'].shift(-steps_shift)


    # Finite differences
    df['vx_abs_filtered'] = (shifted_x2 - shifted_x0) / (shifted_time2 - shifted_time0)
    df['vy_abs_filtered'] = (shifted_y2 - shifted_y0) / (shifted_time2 - shifted_time0)
    df['w']  = (shifted_yaw2 - shifted_yaw0) / (shifted_time2 - shifted_time0)

    # Handle the last 5 elements (they will be NaN due to the shift)
    df['vx_abs_filtered'].iloc[-steps_shift:] = 0
    df['vy_abs_filtered'].iloc[-steps_shift:] = 0
    df['w'].iloc[-steps_shift:] = 0

    df['vx_abs_filtered'].iloc[:steps_shift] = 0
    df['vy_abs_filtered'].iloc[:steps_shift] = 0
    df['w'].iloc[:steps_shift] = 0


    # --- evalaute second time derivative ---
    # Shifted values for steps_shift indices ahead
    shifted_vx0 = df['vx_abs_filtered'].shift(+steps_shift)
    shifted_vy0 = df['vy_abs_filtered'].shift(+steps_shift)
    shifted_w0 = df['w'].shift(+steps_shift)

    shifted_vx2 = df['vx_abs_filtered'].shift(-steps_shift)
    shifted_vy2 = df['vy_abs_filtered'].shift(-steps_shift)
    shifted_w2 = df['w'].shift(-steps_shift)

    # Calculate the finite differences for acceleration
    df['ax_abs_filtered_more'] = (shifted_vx2 - shifted_vx0) / (shifted_time2 - shifted_time0)
    df['ay_abs_filtered_more'] = (shifted_vy2 - shifted_vy0) / (shifted_time2 - shifted_time0)
    df['acc_w'] = (shifted_w2 - shifted_w0) / (shifted_time2 - shifted_time0)

    # Handle the last 5 elements (they will be NaN due to the shift)
    df['ax_abs_filtered_more'].iloc[-steps_shift:] = 0
    df['ay_abs_filtered_more'].iloc[-steps_shift:] = 0
    df['acc_w'].iloc[-steps_shift:] = 0

    df['ax_abs_filtered_more'].iloc[:steps_shift] = 0
    df['ay_abs_filtered_more'].iloc[:steps_shift] = 0
    df['acc_w'].iloc[:steps_shift] = 0


    # --- convert velocity and acceleration into body frame ---
    vx_body_vec = np.zeros(df.shape[0])
    vy_body_vec = np.zeros(df.shape[0])
    ax_body_vec_nocent = np.zeros(df.shape[0])
    ay_body_vec_nocent = np.zeros(df.shape[0])

    for i in range(df.shape[0]):
        rot_angle =  - df['unwrapped yaw'].iloc[i] # from global to body you need to rotate by -theta!

        R     = np.array([[ np.cos(rot_angle), -np.sin(rot_angle)],
                          [ np.sin(rot_angle),  np.cos(rot_angle)]])
        

        vxvy = np.expand_dims(np.array(df[['vx_abs_filtered','vy_abs_filtered']].iloc[i]),1)
        axay = np.expand_dims(np.array(df[['ax_abs_filtered_more','ay_abs_filtered_more']].iloc[i]),1)

        vxvy_body = R @ vxvy
        axay_nocent = R @ axay

        vx_body_vec[i],vy_body_vec[i] = vxvy_body[0], vxvy_body[1]
        ax_body_vec_nocent[i],ay_body_vec_nocent[i] = axay_nocent[0], axay_nocent[1]

    df['vx body'] = vx_body_vec
    df['vy body'] = vy_body_vec

    df['ax body no centrifugal'] = ax_body_vec_nocent
    df['ay body no centrifugal'] = ay_body_vec_nocent

    # add acceleration in own body frame
    accx_cent = + df['vy body'].to_numpy() * df['w'].to_numpy() 
    accy_cent = - df['vx body'].to_numpy() * df['w'].to_numpy()

    # add centrifugal forces to df
    df['ax body'] = accx_cent + df['ax body no centrifugal'].to_numpy()
    df['ay body'] = accy_cent + df['ay body no centrifugal'].to_numpy()
    return df


def process_raw_vicon_data(df,steps_shift):
    print('Processing dynamics data')

    mf = model_functions() # instantiate the model functions object

    # process kinematics from vicon data
    #df = process_vicon_data_kinematics(df,steps_shift,theta_correction, l_COM, l_lateral_shift_reference)

    # Evaluate steering angle and slip angles as they can be useful to tweak the parameters relative to the measuring system
    
    # evaluate steering angle if it is not provided
    # if 'steering angle' in df.columns:
    #     steering_angle = df['steering angle'].to_numpy()
    # else:
    steering_angle = mf.steering_2_steering_angle(df['steering'].to_numpy(),
                                                            mf.a_s_self,
                                                            mf.b_s_self,
                                                            mf.c_s_self,
                                                            mf.d_s_self,
                                                            mf.e_s_self)
    df['steering angle'] = steering_angle 


    # if the provided data has the forward euler integrated inputs i.e. it has the input dynamics data, then use that instead
    if 'steering angle filtered' in df.columns:
        steering_angle = df['steering angle filtered'].to_numpy()
    else:
        steer_angle = df['steering angle'].to_numpy()






    df['Vx_wheel_front'] =  np.cos(-steering_angle) * df['vx body'].to_numpy() - np.sin(-steering_angle)*(df['vy body'].to_numpy() + mf.lf_self*df['w'].to_numpy())
    
    # evaluate slip angles
    a_slip_f, a_slip_r = mf.evaluate_slip_angles(df['vx body'].to_numpy(),df['vy body'].to_numpy(),df['w'].to_numpy(),mf.lf_self,mf.lr_self,steering_angle)

    # add new columns
    df['slip angle front'] = a_slip_f
    df['slip angle rear'] = a_slip_r


    # -----     DYNAMICS      ------
    # evaluate forces in body frame starting from the ones in the absolute frame
    Fx_wheel_vec = np.zeros(df.shape[0])
    Fy_r_wheel_vec = np.zeros(df.shape[0])
    Fy_f_wheel_vec = np.zeros(df.shape[0])

    # evalauting lateral velocities on wheels
    V_y_f_wheel = np.zeros(df.shape[0])

    # evaluate lateral forces from lateral and yaw dynamics
    for i in range(0,df.shape[0]):

        # ax body no centrifugal are just the forces rotated by the yaw angle
        b = np.array([df['ax body no centrifugal'].iloc[i]*mf.m_self,
                      df['ay body no centrifugal'].iloc[i]*mf.m_self,
                     (df['acc_w'].iloc[i])*mf.Jz_self]) 
        
        steer_angle = steering_angle[i] # df['steering angle'].iloc[i]
        
        # accounting for static load partitioning on Fx
        c_front = (mf.m_front_wheel_self)/mf.m_self
        c_rear = (mf.m_rear_wheel_self)/mf.m_self

        A = np.array([[+c_front * np.cos(steer_angle) + c_rear * 1,-np.sin(steer_angle)     , 0],
                      [+c_front * np.sin(steer_angle)             ,+np.cos(steer_angle)     , 1],
                      [+c_front * mf.lf_self * np.sin(steer_angle)        , mf.lf_self * np.cos(steer_angle),-mf.lr_self]])
        
        [Fx_i_wheel, Fy_f_wheel, Fy_r_wheel] = np.linalg.solve(A, b)

        Fx_wheel_vec[i]   = Fx_i_wheel
        Fy_f_wheel_vec[i] = Fy_f_wheel
        Fy_r_wheel_vec[i] = Fy_r_wheel
        

        # evaluate wheel lateral velocities
        V_y_f_wheel[i] = np.cos(steer_angle)*(df['vy body'].to_numpy()[i] + mf.lf_self*df['w'].to_numpy()[i]) - np.sin(steer_angle) * df['vx body'].to_numpy()[i]
    V_y_r_wheel = df['vy body'].to_numpy() - mf.lr_self*df['w'].to_numpy()

    # add new columns
    df['Fx wheel'] = Fx_wheel_vec  # this is the force on a single wheel
    df['Fy front wheel'] = Fy_f_wheel_vec
    df['Fy rear wheel'] = Fy_r_wheel_vec
    df['V_y front wheel'] = V_y_f_wheel
    df['V_y rear wheel'] = V_y_r_wheel

    return df


def unwrap_hm(x):  # this function is used to unwrap the angles
    if isinstance(x, (int, float)):
        return np.unwrap([x])[0]
    elif isinstance(x, np.ndarray):
        return np.unwrap(x)
    else:
        raise ValueError("Invalid input type. Expected 'float', 'int', or 'numpy.ndarray'.")



def plot_vicon_data(df):

    # plot vicon data filtering process
    plotting_time_vec = df['vicon time'].to_numpy()

    fig1, ((ax1, ax2, ax3),(ax4, ax5, ax6)) = plt.subplots(2, 3, figsize=(10, 6), constrained_layout=True)
    ax1.set_title('velocity x')
    #ax1.plot(plotting_time_vec, df['vx_abs_raw'].to_numpy(), label="vicon abs vx raw", color='k')
    ax1.plot(plotting_time_vec, df['vx_abs_filtered'].to_numpy(), label="vicon abs vx filtered", color='dodgerblue')
    ax1.legend()

    ax4.set_title('acceleration x')
    #ax4.plot(plotting_time_vec, df['ax_abs_raw'].to_numpy(), label="vicon abs ax raw", color='k')
    #ax4.plot(plotting_time_vec, df['ax_abs_filtered'].to_numpy(), label="vicon abs ax filtered", color='k')
    ax4.plot(plotting_time_vec, df['ax_abs_filtered_more'].to_numpy(), label="vicon abs ax filtered more", color='dodgerblue')
    ax4.legend()


    ax2.set_title('velocity y')
    #ax2.plot(plotting_time_vec, df['vy_abs_raw'].to_numpy(), label="vicon abs vy raw", color='k')
    ax2.plot(plotting_time_vec, df['vy_abs_filtered'].to_numpy(), label="vicon abs vy filtered", color='orangered')
    ax2.legend()

    ax5.set_title('acceleration y')
    #ax5.plot(plotting_time_vec, df['ay_abs_raw'].to_numpy(), label="vicon abs ay raw", color='k')
    #ax5.plot(plotting_time_vec, df['ay_abs_filtered'].to_numpy(), label="vicon abs ay filtered", color='k')
    ax5.plot(plotting_time_vec, df['ay_abs_filtered_more'].to_numpy(), label="vicon abs ay filtered more", color='orangered')
    ax5.legend()


    ax3.set_title('velocity yaw')
    #ax3.plot(plotting_time_vec, df['w_abs_raw'].to_numpy(), label="vicon w raw", color='k')
    ax3.plot(plotting_time_vec, df['w'].to_numpy(), label="vicon w filtered", color='slateblue')
    ax3.legend()

    ax6.set_title('acceleration yaw')
    #ax6.plot(plotting_time_vec, df['aw_abs_raw'].to_numpy(), label="vicon aw raw", color='k')
    #ax6.plot(plotting_time_vec, df['aw_abs_filtered'].to_numpy(), label="vicon aw filtered", color='k')
    ax6.plot(plotting_time_vec, df['acc_w'].to_numpy(), label="vicon aw filtered more", color='slateblue')
    ax6.legend()





    # plot raw opti data
    fig1, ((ax1, ax2, ax3 , ax4)) = plt.subplots(4, 1, figsize=(10, 6), constrained_layout=True)
    ax1.set_title('Velocity data')
    #ax1.plot(plotting_time_vec, df['vx_abs'].to_numpy(), label="Vx abs data", color='lightblue')
    #ax1.plot(plotting_time_vec, df['vy_abs'].to_numpy(), label="Vy abs data", color='rosybrown')
    ax1.plot(plotting_time_vec, df['vx body'].to_numpy(), label="Vx body", color='dodgerblue')
    ax1.plot(plotting_time_vec, df['vy body'].to_numpy(), label="Vy body", color='orangered')
    ax1.legend()

    # plot body frame data time history
    ax2.set_title('Vy data raw vicon')
    ax2.plot(plotting_time_vec, df['throttle'].to_numpy(), label="Throttle",color='gray', alpha=1)
    ax2.plot(plotting_time_vec, df['vel encoder'].to_numpy(),label="Velocity Encoder raw", color='indigo')
    ax2.plot(plotting_time_vec, df['vx body'].to_numpy(), label="Vx body frame",color='dodgerblue')
    ax2.plot(plotting_time_vec, df['Vx_wheel_front'].to_numpy(), label="Vx front wheel",color='navy')
    #ax2.plot(plotting_time_vec, df['vy body'].to_numpy(), label="Vy body frame",color='orangered')
    
    ax2.legend()
    # plot omega data time history
    ax3.set_title('Omega data time history')
    ax3.plot(plotting_time_vec, df['steering'].to_numpy(),label="steering input raw data", color='pink') #  -17 / 180 * np.pi * 
    ax3.plot(plotting_time_vec, df['W (IMU)'].to_numpy(),label="omega IMU raw data", color='orchid')
    #ax3.plot(plotting_time_vec, df['w_abs'].to_numpy(), label="omega opti", color='lightblue')
    ax3.plot(plotting_time_vec, df['w'].to_numpy(), label="omega opti filtered",color='slateblue')
    ax3.legend()

    ax4.set_title('x - y - theta time history')
    ax4.plot(plotting_time_vec, df['vicon x'].to_numpy(), label="x opti",color='slateblue')
    ax4.plot(plotting_time_vec, df['vicon y'].to_numpy(), label="y opti",color='orangered')
    ax4.plot(plotting_time_vec, df['unwrapped yaw'].to_numpy(), label="unwrapped theta",color='yellowgreen')
    ax4.plot(plotting_time_vec, df['vicon yaw'].to_numpy(), label="theta raw data", color='darkgreen')
    ax4.legend()


    # plot slip angles
    fig2, ((ax1, ax2, ax3)) = plt.subplots(3, 1, figsize=(10, 6), constrained_layout=True)
    ax1.set_title('slip angle front')
    ax1.plot(plotting_time_vec, df['slip angle front'].to_numpy(), label="slip angle front", color='peru')
    ax1.plot(plotting_time_vec, df['slip angle rear'].to_numpy(), label="slip angle rear", color='darkred')
    # ax1.plot(plotting_time_vec, df['acc_w'].to_numpy(), label="acc w", color='slateblue')
    # ax1.plot(plotting_time_vec, df['vy body'].to_numpy(), label="Vy body", color='orangered')
    # ax1.plot(plotting_time_vec, df['vx body'].to_numpy(), label="Vx body", color='dodgerblue')
    ax1.legend()

    ax2.set_title('Wheel lateral velocities')
    ax2.plot(plotting_time_vec, df['V_y front wheel'].to_numpy(), label="V_y rear wheel", color='peru')
    ax2.plot(plotting_time_vec, df['V_y rear wheel'].to_numpy(), label="V_y front wheel", color='darkred')
    ax2.legend()


    ax3.set_title('Normalized Steering and acc W')
    ax3.plot(plotting_time_vec, df['acc_w'].to_numpy()/df['acc_w'].max(), label="acc w normalized", color='slateblue')
    ax3.plot(plotting_time_vec, df['steering'].to_numpy()/df['steering'].max(), label="steering normalized", color='purple')
    #ax3.plot(df['vicon time'].to_numpy(),df['steering angle time delayed'].to_numpy()/df['steering angle time delayed'].max(),label='steering angle time delayed normalized',color='k')
    ax3.legend()


    # instantiate the model functions object to instantiate the fitted model parameters
    mf = model_functions() 




    # plot Wheel velocity vs force data
    fig1, ((ax_wheel_f_alpha,ax_wheel_r_alpha)) = plt.subplots(1, 2, figsize=(10, 6), constrained_layout=True)
    # determine x limits
    x_lim_alpha = [np.min([df['slip angle rear'].min(),df['slip angle front'].min()]),
             np.max([df['slip angle rear'].max(),df['slip angle front'].max()])]
    
    # evaluate wheel curve
    slip_angles_to_plot = np.linspace(x_lim_alpha[0],x_lim_alpha[1],100)
    wheel_curve_f = mf.lateral_tire_force(slip_angles_to_plot,
                                              mf.d_t_f_self,
                                              mf.c_t_f_self,
                                              mf.b_t_f_self,
                                              mf.m_front_wheel_self)



    wheel_curve_r = mf.lateral_tire_force(slip_angles_to_plot,
                                              mf.d_t_r_self,
                                              mf.c_t_r_self,
                                              mf.b_t_r_self,
                                              mf.m_rear_wheel_self)

    
    y_lim_alpha = [np.min([df['Fy front wheel'].min(),df['Fy rear wheel'].min()]),
                   np.max([df['Fy front wheel'].max(),df['Fy rear wheel'].max()])]
    
    #color_code_label = 'steering'
    color_code_label = 'ax body'
    #color_code_label = 'ay body'
    cmap = 'Spectral'
    #cmap = 'plasma'

    c_front = df[color_code_label].to_numpy()

    scatter_front = ax_wheel_f_alpha.scatter(df['slip angle front'].to_numpy(),df['Fy front wheel'].to_numpy(),label='front wheel',c=c_front,cmap=cmap,s=3) #df['vel encoder'].to_numpy()- 

    cbar1 = fig1.colorbar(scatter_front, ax=ax_wheel_f_alpha)
    cbar1.set_label(color_code_label)  # Label the colorbar  'vel encoder-vx body'

    #ax_wheel_f.scatter(df['V_y rear wheel'].to_numpy(),df['Fy rear wheel'].to_numpy(),label='rear wheel',color='darkred',s=3)
    scatter_rear = ax_wheel_r_alpha.scatter(df['slip angle rear'].to_numpy(),df['Fy rear wheel'].to_numpy(),label='rear wheel',c=c_front,cmap=cmap,s=3)

    #add wheel curve
    ax_wheel_f_alpha.plot(slip_angles_to_plot,wheel_curve_f,color='silver',label='Tire model',linewidth=4,linestyle='--')
    ax_wheel_r_alpha.plot(slip_angles_to_plot,wheel_curve_r,color='silver',label='Tire model',linewidth=4,linestyle='--')


    ax_wheel_f_alpha.scatter(np.array([0.0]),np.array([0.0]),color='orangered',label='zero',marker='+', zorder=20) # plot zero as an x 
    ax_wheel_r_alpha.scatter(np.array([0.0]),np.array([0.0]),color='orangered',label='zero',marker='+', zorder=20) # plot zero as an x

    ax_wheel_r_alpha.set_xlabel('slip angle [rad]')
    ax_wheel_r_alpha.set_ylabel('Fy')
    ax_wheel_r_alpha.set_xlim(x_lim_alpha[0],x_lim_alpha[1])
    ax_wheel_r_alpha.set_ylim(y_lim_alpha[0],y_lim_alpha[1])
    ax_wheel_r_alpha.legend()


    ax_wheel_f_alpha.set_xlabel('slip angle [rad]') 
    ax_wheel_f_alpha.set_ylabel('Fy')
    ax_wheel_f_alpha.set_xlim(x_lim_alpha[0],x_lim_alpha[1])
    ax_wheel_f_alpha.set_ylim(y_lim_alpha[0],y_lim_alpha[1])
    ax_wheel_f_alpha.legend()
    ax_wheel_f_alpha.set_title('Wheel lateral forces')
    #colorbar = fig1.colorbar(scatter, label='steering angle time delayed derivative')
 















    # plot dt data to check no jumps occur
    fig1, ((ax1)) = plt.subplots(1, 1, figsize=(10, 6), constrained_layout=True)
    ax1.plot(df['vicon time'].to_numpy(),df['vicon time'].diff().to_numpy())
    ax1.set_title('time steps')

    # plot acceleration data
    fig1, ((ax1, ax2, ax3),(ax_acc_x_body, ax_acc_y_body, ax_acc_w)) = plt.subplots(2, 3, figsize=(10, 6), constrained_layout=True)
    ax1.plot(df['vicon time'].to_numpy(), df['ax body no centrifugal'].to_numpy(),label='acc x absolute measured in body frame',color = 'dodgerblue')
    ax1.set_xlabel('time [s]')
    ax1.set_title('X_ddot @ R(yaw)')
    ax1.legend()

    ax2.plot(df['vicon time'].to_numpy(), df['ay body no centrifugal'].to_numpy(),label='acc y absolute measured in body frame',color = 'orangered')
    ax2.set_xlabel('time [s]')
    ax2.set_title('Y_ddot @ R(yaw)')
    ax2.legend()

    ax3.plot(df['vicon time'].to_numpy(), df['acc_w'].to_numpy(),label='dt',color = 'slateblue')
    ax3.set_xlabel('time [s]')
    ax3.set_title('Acc w')
    ax3.legend()

    # plot accelerations in the body frame
    ax_acc_x_body.plot(df['vicon time'].to_numpy(), df['ax body'].to_numpy(),label='acc x in body frame',color = 'dodgerblue')
    ax_acc_x_body.set_xlabel('time [s]')
    ax_acc_x_body.set_title('X_ddot @ R(yaw) + cent')
    ax_acc_x_body.legend()

    ax_acc_y_body.plot(df['vicon time'].to_numpy(), df['ay body'].to_numpy(),label='acc y in body frame',color = 'orangered')
    ax_acc_y_body.set_xlabel('time [s]')
    ax_acc_y_body.set_title('Y_ddot @ R(yaw) + cent')
    ax_acc_y_body.legend()

    ax_acc_w.plot(df['vicon time'].to_numpy(), df['acc_w'].to_numpy(),label='acc w',color = 'slateblue')
    ax_acc_w.set_xlabel('time [s]')
    ax_acc_w.set_title('Acc w')
    ax_acc_w.legend()




    # plot x-y trajectory
    plt.figure()
    plt.plot(df['vicon x'].to_numpy(),df['vicon y'].to_numpy())
    plt.title('x-y trajectory')

    # plot the steering angle time delayed vs W  Usefull to get the steering delay right
    plt.figure()
    plt.title('steering angle time delayed vs W nomalized')
    plt.plot(df['vicon time'].to_numpy(),df['steering angle'].to_numpy()/df['steering angle'].max(),label='steering angle normalized')
    #plt.plot(df['vicon time'].to_numpy(),df['steering angle time delayed'].to_numpy()/df['steering angle time delayed'].max(),label='steering angle time delayed normalized')
    plt.plot(df['vicon time'].to_numpy(),df['w'].to_numpy()/df['w'].max(),label='w filtered normalized')
    plt.legend()


    #plot wheel force saturation
    # plot acceleration data
    # evaluate total wheel forces abs value
    Fy_f_wheel_abs = (df['Fy front wheel'].to_numpy()**2 + df['Fx wheel'].to_numpy()**2)**0.5
    Fy_r_wheel_abs = (df['Fy rear wheel'].to_numpy()**2 + df['Fx wheel'].to_numpy()**2)**0.5

    wheel_slippage = np.abs(df['vel encoder'].to_numpy() - df['vx body'].to_numpy())

    fig1, ((ax_total_force_front,ax_total_force_rear)) = plt.subplots(2, 1, figsize=(10, 6), constrained_layout=True)
    ax_total_force_front.plot(df['vicon time'].to_numpy(), Fy_f_wheel_abs,label='Total wheel force front',color = 'peru')
    ax_total_force_front.plot(df['vicon time'].to_numpy(), wheel_slippage,label='longitudinal slippage',color = 'gray')
    ax_total_force_front.plot(df['vicon time'].to_numpy(), df['ax body no centrifugal'].to_numpy(),label='longitudinal acceleration',color = 'dodgerblue')
    ax_total_force_front.plot(df['vicon time'].to_numpy(), df['ay body no centrifugal'].to_numpy(),label='lateral acceleration',color = 'orangered')
    ax_total_force_front.set_xlabel('time [s]')
    ax_total_force_front.set_title('Front total wheel force')
    ax_total_force_front.legend()

    ax_total_force_rear.plot(df['vicon time'].to_numpy(), Fy_r_wheel_abs,label='Total wheel force rear',color = 'darkred')
    ax_total_force_rear.plot(df['vicon time'].to_numpy(), wheel_slippage,label='longitudinal slippage',color = 'gray')
    ax_total_force_rear.plot(df['vicon time'].to_numpy(), df['ax body no centrifugal'].to_numpy(),label='longitudinal acceleration',color = 'dodgerblue')
    ax_total_force_rear.plot(df['vicon time'].to_numpy(), df['ay body no centrifugal'].to_numpy(),label='lateral acceleration',color = 'orangered')
    ax_total_force_rear.set_xlabel('time [s]')
    ax_total_force_rear.set_title('Rear total wheel force')
    ax_total_force_rear.legend()

    # plotting forces
    fig1, ((ax_lat_force,ax_long_force)) = plt.subplots(2, 1, figsize=(10, 6), constrained_layout=True)
    accx_cent = + df['vy body'].to_numpy() * df['w'].to_numpy() 
    accy_cent = - df['vx body'].to_numpy() * df['w'].to_numpy() 
    ax_lat_force.plot(df['vicon time'].to_numpy(), df['Fy front wheel'].to_numpy(),label='Fy front measured',color = 'peru')
    ax_lat_force.plot(df['vicon time'].to_numpy(), df['Fy rear wheel'].to_numpy(),label='Fy rear measured',color = 'darkred')
    ax_lat_force.plot(df['vicon time'].to_numpy(), wheel_slippage,label='longitudinal slippage',color = 'gray')
    ax_lat_force.plot(df['vicon time'].to_numpy(), accx_cent + df['ax body no centrifugal'].to_numpy(),label='longitudinal acceleration (with cent))',color = 'dodgerblue')
    ax_lat_force.plot(df['vicon time'].to_numpy(), accy_cent + df['ay body no centrifugal'].to_numpy(),label='lateral acceleration (with cent)',color = 'orangered')
    ax_lat_force.set_xlabel('time [s]')
    ax_lat_force.set_title('Lateral wheel forces')
    ax_lat_force.legend()

    ax_long_force.plot(df['vicon time'].to_numpy(), df['Fx wheel'].to_numpy(),label='longitudinal forces',color = 'dodgerblue')
    ax_long_force.plot(df['vicon time'].to_numpy(), wheel_slippage,label='longitudinal slippage',color = 'gray')
    ax_long_force.set_xlabel('time [s]')
    ax_long_force.set_title('Longitudinal wheel force')
    ax_long_force.legend()



    return ax_wheel_f_alpha,ax_wheel_r_alpha,ax_total_force_front,\
ax_total_force_rear,ax_lat_force,ax_long_force,\
ax_acc_x_body,ax_acc_y_body,ax_acc_w



def produce_long_term_predictions(input_data, model,prediction_window,jumps,forward_propagate_indexes):
    # plotting long term predictions on data
    # each prediction window starts from a data point and then the quantities are propagated according to the provided model,
    # so they are not tied to the Vx Vy W data in any way. Though the throttle and steering inputs are taken from the data of course.

    # --- plot fitting results ---
    # input_data = 'vicon time', 'vx body', 'vy body', 'w', 'throttle filtered' ,'steering filtered', 'throttle' ,'steering','vicon x','vicon y','vicon yaw'

    #prepare tuple containing the long term predictions
    n_states = 5
    n_inputs = 2

    states_list = list(range(1,n_states+1))

    long_term_preds = ()
    


    # iterate through each prediction window
    print('------------------------------')
    print('producing long term predictions')
    from tqdm import tqdm
    tqdm_obj = tqdm(range(0,input_data.shape[0],jumps), desc="long term preds", unit="pred")

    for i in tqdm_obj:
        

        #reset couner
        k = 0
        elpsed_time_long_term_pred = 0

        # set up initial states
        long_term_pred = np.expand_dims(input_data[i, :],0)


        # iterate through time indexes of each prediction window
        while elpsed_time_long_term_pred < prediction_window and k + i + 1 < len(input_data):
            #store time values
            #long_term_pred[k+1,0] = input_data[k+i, 0] 

            dt = input_data[i + k + 1, 0] - input_data[i + k, 0]
            elpsed_time_long_term_pred = elpsed_time_long_term_pred + dt

            #produce propagated state
            state_action_k = long_term_pred[k,1:n_states+n_inputs+1]
            
            # run it through the model
            accelerations = model.forward(state_action_k) # absolute accelerations in the current vehicle frame of reference
            
            # evaluate new state
            new_state_new_frame_candidate = long_term_pred[k,1:n_states+1] + accelerations * dt 

            # Initialize the new state
            new_state_new_frame = np.zeros(n_states)

            # Forward propagate the quantities (vx, vy, w)
            for idx in states_list: 
                if idx in forward_propagate_indexes:
                    new_state_new_frame[idx-1] = new_state_new_frame_candidate[idx-1]
                else:
                    new_state_new_frame[idx-1] = input_data[i + k + 1, idx] # no mius one here because the first entry is time

        

            # forward propagate x y yaw state
            x_index = n_states+n_inputs+1
            y_index = n_states+n_inputs+2
            yaw_index = n_states+n_inputs+3

            rot_angle = long_term_pred[k,yaw_index] # extract yaw angle
            R = np.array([
                [np.cos(rot_angle), -np.sin(rot_angle), 0],
                [np.sin(rot_angle), np.cos(rot_angle), 0],
                [0, 0, 1]
            ])

            # absolute velocities
            abs_vxvyw = R @ np.array([long_term_pred[k,1],long_term_pred[k,2],long_term_pred[k,3]])

            # propagate x y yaw according to the previous state
            new_xyyaw = np.array([long_term_pred[k,x_index],long_term_pred[k,y_index],long_term_pred[k,yaw_index]]) + abs_vxvyw * dt

            # put everything together
            current_time_index = i + k + 1
            new_row = np.array([input_data[current_time_index, 0], # time
                                *new_state_new_frame,
                                input_data[current_time_index,n_states+1], # throttle input
                                input_data[current_time_index,n_states+2], # steering input
                                *new_xyyaw])
            
            long_term_pred = np.vstack([long_term_pred, new_row])

            # update k
            k = k + 1

        long_term_preds += (long_term_pred,)  

    return long_term_preds



class dyn_model_culomb_tires(model_functions):
    def __init__(self,steering_friction_flag,pitch_dynamics_flag):

        self.pitch_dynamics_flag = pitch_dynamics_flag
        self.steering_friction_flag = steering_friction_flag


        if self.pitch_dynamics_flag:
            self.w_natural_pitch = self.w_natural_Hz_pitch_self * 2 *np.pi
            self.c_pitch = 2 * self.w_natural_pitch 
            self.k_pitch_dynamics = self.w_natural_pitch**2

            # evaluate influence coefficients based on equilibrium of moments
            l_tilde = -0.5*self.lf_self**2-0.5*self.lr_self**2-self.lf_self*self.lr_self
            l_star = (self.lf_self-self.lr_self)/2
            self.k_pitch_front = self.k_pitch_self * (+self.lf_self + l_star)/l_tilde  / 9.81 



    def forward(self, state_action):
        #returns vx_dot,vy_dot,w_dot in the vehicle body frame
        #state_action = [vx,vy,w,throttle,steer,pitch,pitch_dot,roll,roll_dot]
        vx = state_action[0]
        vy = state_action[1]
        w = state_action[2]
        throttle = state_action[3]
        steering = state_action[4]
        throttle_command = state_action[5]
        steering_command = state_action[6]


        # # convert steering to steering angle
        steer_angle = self.steering_2_steering_angle(steering,self.a_s_self,self.b_s_self,self.c_s_self,self.d_s_self,self.e_s_self)

        # if using pitch dynamics account for the extra load on front tires (you also need to enable the input dynamics)
        if self.pitch_dynamics_flag:
            pitch_dot = state_action[7]
            pitch = state_action[8]
            # evaluate pitch contribution
            normal_force_non_scaled = pitch + self.c_pitch/self.k_pitch_dynamics * pitch_dot
            additional_load_front = self.k_pitch_front * normal_force_non_scaled
        else:
            additional_load_front = 0



    
        # # evaluate longitudinal forces
        Fx_wheels = + self.motor_force(throttle,vx,self.a_m_self,self.b_m_self,self.c_m_self)\
                    + self.rolling_friction(vx,self.a_f_self,self.b_f_self,self.c_f_self,self.d_f_self)
        # add extra friction due to steering
        if self.steering_friction_flag:
            Fx_wheels += self.F_friction_due_to_steering(steer_angle,vx,self.a_stfr_self,self.b_stfr_self,self.d_stfr_self,self.e_stfr_self)



        c_front = (self.m_front_wheel_self)/self.m_self
        c_rear = (self.m_rear_wheel_self)/self.m_self

        # redistribute Fx to front and rear wheels according to normal load
        Fx_front = Fx_wheels * c_front
        Fx_rear = Fx_wheels * c_rear

        #evaluate slip angles
        alpha_f,alpha_r = self.evaluate_slip_angles(vx,vy,w,self.lf_self,self.lr_self,steer_angle)

        #lateral forces
        Fy_wheel_f = self.lateral_tire_force(alpha_f,self.d_t_f_self,self.c_t_f_self,self.b_t_f_self,self.m_front_wheel_self + additional_load_front)
        Fy_wheel_r = self.lateral_tire_force(alpha_r,self.d_t_r_self,self.c_t_r_self,self.b_t_r_self,self.m_rear_wheel_self)

        acc_x,acc_y,acc_w = self.solve_rigid_body_dynamics(vx,vy,w,steer_angle,Fx_front,Fx_rear,Fy_wheel_f,Fy_wheel_r,self.lf_self,self.lr_self,self.m_self,self.Jz_self)


        # evaluate input dynamics
        throttle_dot = self.continuous_time_1st_order_dynamics(throttle,throttle_command,self.d_m_self)
        steering_dot = self.continuous_time_1st_order_dynamics(steering,steering_command,self.k_stdn_self)



        if self.pitch_dynamics_flag:
            # solve pitch dynamics
            pitch_dot_dot = self.critically_damped_2nd_order_dynamics_numpy(pitch_dot,pitch,acc_x,self.w_natural_Hz_pitch_self)




        if self.pitch_dynamics_flag:
            return np.array([acc_x,acc_y,acc_w,throttle_dot,steering_dot, pitch_dot_dot, pitch_dot])
        else:
            return np.array([acc_x,acc_y,acc_w,throttle_dot,steering_dot])
   

class dyn_model_culomb_tires_pitch(dyn_model_culomb_tires):
    def __init__(self,dyn_model_culomb_tires_obj):
        self.dyn_model_culomb_tires_obj = dyn_model_culomb_tires_obj

        



    def forward(self,state_action):
        # forward the usual dynamic model
        #   'vx body',      0
        #   'vy body',      1
        #   'w',        2
        #   'throttle integrated' ,  3
        #   'steering integrated',   4
        #   'pitch dot',    5
        #   'pitch',        6
        #   'throttle',     7
        #   'steering',     8



        state_action_base_model = state_action[:7]
        [acc_x,acc_y,acc_w, pitch_dot_dot, pitch_dot] = self.dyn_model_culomb_tires_obj.forward(state_action_base_model) # forward base model
        
        # extract axuliary states
        throttle = state_action[3]
        steering = state_action[4]

        throttle_command = state_action[7]
        steering_command = state_action[8]
        
        
        # forwards integrate steering and throttle commands
        throttle_time_constant = 0.1 * self.d_m_self / (1 + self.d_m_self) # converting from discrete time to continuous time
        throttle_dot = (throttle_command - throttle) / throttle_time_constant

        # steering dynamics
        st_dot = (steering_command - steering) / 0.01 * self.k_stdn_self

        return [acc_x,acc_y,acc_w, pitch_dot_dot, pitch_dot,throttle_dot,st_dot]



def produce_long_term_predictions_full_model(input_data, model,prediction_window,jumps,forward_propagate_indexes):
    # plotting long term predictions on data
    # each prediction window starts from a data point and then the quantities are propagated according to the provided model,
    # so they are not tied to the Vx Vy W data in any way. Though the throttle and steering inputs are taken from the data of course.

    # --- plot fitting results ---
    # input_data = ['vicon time',   0
                #   'vx body',      1
                #   'vy body',      2
                #   'w',        3
                #   'throttle integrated' ,  4
                #   'steering integrated',   5
                #   'pitch dot',    6
                #   'pitch',        7
                #   'throttle',     8
                #   'steering',     9
                #   'vicon x',      10
                #   'vicon y',      11
                #   'vicon yaw']    12

    #prepare tuple containing the long term predictions
    long_term_preds = ()
    

    # iterate through each prediction window
    print('------------------------------')
    print('producing long term predictions')
    from tqdm import tqdm
    tqdm_obj = tqdm(range(0,input_data.shape[0],jumps), desc="long term preds", unit="pred")

    for i in tqdm_obj:
        
        #reset couner
        k = 0
        elpsed_time_long_term_pred = 0

        # set up initial positions
        long_term_pred = np.expand_dims(input_data[i, :],0)


        # iterate through time indexes of each prediction window
        while elpsed_time_long_term_pred < prediction_window and k + i + 1 < len(input_data):
            #store time values
            #long_term_pred[k+1,0] = input_data[k+i, 0] 
            dt = input_data[i + k + 1, 0] - input_data[i + k, 0]
            elpsed_time_long_term_pred = elpsed_time_long_term_pred + dt

            #produce propagated state
            state_action_k = long_term_pred[k,1:10]
            
            # run it through the model (forward the full model)
            accelerations = model.forward(state_action_k) # absolute accelerations in the current vehicle frame of reference
            



            # evaluate new state
            new_state_new_frame = np.zeros(7)

            for prop_index in range(1,7):
                # chose quantities to forward propagate
                if prop_index in forward_propagate_indexes:
                    new_state_new_frame[prop_index-1] = long_term_pred[k,prop_index] + accelerations[prop_index-1] * dt 
                else:
                    new_state_new_frame[prop_index-1] = input_data[i+k+1, prop_index]


            # forward propagate x y yaw state
            rot_angle = long_term_pred[k,12]
            R = np.array([
                [np.cos(rot_angle), -np.sin(rot_angle), 0],
                [np.sin(rot_angle), np.cos(rot_angle), 0],
                [0, 0, 1]
            ])

            # absolute velocities from previous time instant
            abs_vxvyw = R @ np.array([long_term_pred[k,1],long_term_pred[k,2],long_term_pred[k,3]])


            # propagate x y yaw according to the previous state
            new_xyyaw = np.array([long_term_pred[k,10],long_term_pred[k,11],long_term_pred[k,12]]) + abs_vxvyw * dt

            # put everything together
            new_row = np.array([input_data[i + k + 1, 0],*new_state_new_frame,input_data[i+k+1,8],input_data[i+k+1,9],*new_xyyaw])
            long_term_pred = np.vstack([long_term_pred, new_row])

            # update k
            k = k + 1

        long_term_preds += (long_term_pred,)  

    return long_term_preds




