import simpy as sp
import random
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd  # Not used at the moment 
from datetime import datetime, timedelta
import seaborn as sns 
import streamlit as st

#Creates the simulation environment 
class AnE:
    
    def __init__(self, env, num_doctors, num_nurses, num_beds, num_clerk,
                 num_immediate, num_very_urgent, num_urgent, num_standard, num_non_urgent,
                 admission_duration, risk_assessment_duration, doctor_consultation_duration, test_duration, medication_duration, follow_up_duration, length_of_stay,
                 probability_discharge, probability_tests, probability_medication
                 ):
        self.env = env
        #Resource Allocation
        self.doctor = sp.PriorityResource(env, num_doctors)
        self.nurse = sp.PriorityResource(env, num_nurses)
        self.bed = sp.Resource(env, num_beds)
        self.clerk = sp.Resource(env, num_clerk) 

        #This is for the triage calculation
        self.num_immediate = num_immediate
        self.num_very_urgent = num_very_urgent
        self.num_urgent = num_urgent
        self.num_standard = num_standard
        self.num_non_urgent = num_non_urgent
       
       #Event Durations
        self.admission_duration = admission_duration
        self.risk_assesment_duration = risk_assessment_duration
        self.doctor_consultation_duration = doctor_consultation_duration
        self.test_duration = test_duration
        self.medication_duration = medication_duration
        self.follow_up_duration = follow_up_duration
        self.length_of_stay = length_of_stay

        # Probablity of discharge, tests and medications
        self.probability_discharge = probability_discharge
        self.probability_tests = probability_tests
        self.probability_medication = probability_medication
       
       
       
       
       
        #self.patient_id=0
        self.patientCount = 0 
        self.active_patients = set()

        self.occupied_beds = 0 #Will increment and decrement 
        self.last_patient_time=0
        #self.priority = 0


        self.start_time = datetime(2025,3,15,8,0)
       
        self.track_bed_usage = [] # This tracks occupied bed over time 
        self.patient_LOS=[] # Length of stay for the patient if they are admitted to a bed
       
        self.patient_spent_time = [] # List the time the patient spent in the A&E


        self.patient_who_waited = [] #List all the wait times for patients who waited
        self.patient_total_wait_time = [] # Total wait times for all the pateints
        
        #This tracks the waiting time for the resources
        self.track_waiting_time_for_clerk = []
        self.track_waiting_time_for_nurse = []
        self.track_waiting_time_for_doctor = []
        self.track_waiting_time_for_bed = []
        
        #This tracks the  time it for the stages of the patient flow - to identify bottlenecks 
        self.track_time_admission = []
        self.track_time_risk_assessment = []
        self.track_time_doctor_consultation = []
        self.track_time_tests = []
        self.track_time_medication = []
        self.track_time_for_follow_up = []
        self.track_time_for_discharge = []


    # This tracks the number of patients in different stages of the process 
        self.num_patient_discharged = 0
        self.num_patient_requires_tests= 0
        self.num_patient_requires_medication = 0
        self.num_patient_requires_bed = 0 
        
        #This tracks the number of patients in the traige categories 
        self.num_patient_immediate = 0
        self.num_patient_very_urgent = 0
        self.num_patient_urgent = 0
        self.num_patient_standard = 0
        self.num_patient_non_urgent = 0

        



    def sim_format_time(self,time):
         current_time = self.start_time + timedelta(minutes=time)
         return current_time.strftime("%H:%M") # This formats the time as hour:minute
    

    def format_in_hours_and_minutes(self, time):
        minutes = time / 60
        return f"{int(minutes) //60}h {int(minutes % 60)}m "

    def update_last_patient_time(self):
              self.last_patient_time = max(self.env.now, self.last_patient_time)
    
    #patient is the process
    def patient_generator(self, mean_interarrival_time, finish_time):
        patient_ID = 0
        while True:
                interarrival_time= np.random.exponential(mean_interarrival_time)
                yield self.env.timeout(interarrival_time) 
                
                if self.env.now > finish_time:
                    continue 
                number_of_patients_arrival = max(1,np.random.poisson(1.5))
                for _ in range(number_of_patients_arrival):
                    self.patientCount +=1 
                    patient_ID+=1
                    self.active_patients.add(patient_ID)
                    with open("patient_log.txt", "a") as output:
                        output.write(f"Patient {patient_ID} arrived at {self.sim_format_time(self.env.now)}" + '\n')
                    self.env.process(self.patient_flow(patient_ID))
                
     #The stages of what the patient goes through
    def patient_flow(self, patient_ID):
        arrival_time=self.env.now #Records when the patient arrives
        yield self.env.process(self.patient_request_admission(patient_ID))
        
        priority=yield self.env.process(self.patient_request_nurse_for_risk_assesment(patient_ID))
        
        #If the patient is immediate, they are assigned to a bed 
        if priority == 0:
             self.num_patient_immediate += 1
             with open("patient_log.txt", "a") as output:
                output.write(f"Patient {patient_ID} is immediate. Assigning a bed at {self.sim_format_time(self.env.now)}" + '\n')
             yield self.env.process(self.patient_request_bed(patient_ID,priority))
             yield self.env.process(self.patient_request_doctor_follow_up(patient_ID,priority))

        else:
             if  priority == 1:
                self.num_patient_very_urgent +=1
             elif priority == 2:
                self.num_patient_urgent +=1
             elif priority== 3:
                self.num_patient_standard +=1
             else:
                self.num_patient_non_urgent +=1


             yield self.env.process(self.patient_request_doctor_for_doctor_consultation(patient_ID, priority))
        
        total_time_patient_spent = self.env.now - arrival_time
        self.patient_spent_time.append(total_time_patient_spent)
        self.active_patients.remove(patient_ID)

    def patient_request_admission(self,patient_ID):
         arrival_time = self.env.now
         with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID} is waiting for a clerk at {self.sim_format_time(self.env.now)}"+ '\n')
         
         #Request general data in the reception 
         req = self.clerk.request()
         yield req 
         
         wait_time = self.env.now - arrival_time
         if wait_time > 0:
            self.track_waiting_time_for_clerk.append(wait_time)

         self.patient_total_wait_time.append(wait_time)
         if wait_time > 0:
            self.patient_who_waited.append(wait_time)
      
         with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID} was assigned a Clerk at {self.sim_format_time(self.env.now)}"+ '\n')

         #Stimulate the admission process
         #yield self.env.timeout(random.randint(1,5))
         yield self.env.timeout(self.admission_duration)
         finish_time = self.env.now
         duration = finish_time - arrival_time
         self.track_time_admission.append(duration)
         with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID}'s admission completed at {self.sim_format_time(self.env.now)}"+ '\n')
         
         #aRelease the clerk
         self.clerk.release(req)
         with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID}'s clerk released at {self.sim_format_time(self.env.now)}"+ '\n')
    
    
    def triage_manchester(self):
        patient_urgency= {
                        "Red (Immediate)": (35,0), # 5% chance of being immediate with 0 being the highest prirority
                        "Orange (Very Urgent)": (10,1), # 10% chance of being very urgent
                        "Yellow (Urgent)": (5,2), #35% chance of being urgent
                        "Green (Standard)": (30,3), #30% chance of being standard
                        "Blue (Non-Urgent)": (20,4) #20% chance of being non-urgent
                    }
        triage_calculator= random.choices(list(patient_urgency.keys()), weights= [value[0] for value in patient_urgency.values()])[0] #Randomly selects a traige based on the weights and then selects the first element from the list
        priority = patient_urgency[triage_calculator][1] #Selects the priority of the selected triage
        return triage_calculator, priority 



     
    def patient_request_nurse_for_risk_assesment (self,patient_ID):
            arrival_time= self.env.now
            #trying to make it  based on patient piriority 
            
            #Request a nurse for risk assessment
            req= self.nurse.request()
            yield req # Wait for the nurse to be availale
            
            wait_time = self.env.now - arrival_time
           
            self.patient_total_wait_time.append(wait_time)
            if wait_time > 0:
                self.patient_who_waited.append(wait_time)
                self.track_waiting_time_for_nurse.append(wait_time)


            with open("patient_log.txt", "a") as output:
                output.write(f"Patient {patient_ID} was assigned a nurse at at {self.sim_format_time(self.env.now)}"+ '\n')
            triage_category, priority = self.triage_manchester()
            with open("patient_log.txt", "a") as output:
                output.write(f"Patient {patient_ID} triaged as {triage_category} priority"+ '\n')


            #Simulate the risk assesment process time
            yield self.env.timeout(self.risk_assessment_duration)
            finish_time = self.env.now
            duration = finish_time - arrival_time
            self.track_time_risk_assessment.append(duration)
            #Release the nurse
            self.nurse.release(req)
            with open("patient_log.txt", "a") as output:
                output.write(f"Patient {patient_ID}'s nurse  was released at {self.sim_format_time(self.env.now)}"+ '\n')
            return priority
    
    def patient_gets_doctor(self,patient_ID):
        arrival_time= self.env.now
       
        #Request a doctor for the patient
        req = self.doctor.request()
        yield req # Wait for the doctor to be avaiable
        
        wait_time = self.env.now - arrival_time
        self.patient_total_wait_time.append(wait_time)
        if wait_time > 0:
            self.patient_who_waited.append(wait_time)
            self.track_waiting_time_for_doctor.append(wait_time)
        
        with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID} was assigned a Doctor assigned at {self.sim_format_time(self.env.now)}"+ '\n')
        yield self.env.timeout(self.doctor_consultation_duration)
        finish_time = self.env.now
        duration = finish_time - arrival_time
        self.track_time_doctor_consultation.append(duration)
        with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID}'s treatment completed at {self.sim_format_time(self.env.now)}"+ '\n')
        self.doctor.release(req)


    def update_bed_occupancy(self):
        self.track_bed_usage.append((self.env.now,self.occupied_beds))


    def patient_request_bed(self,patient_ID,priority):
        arrival_time= self.env.now 
        self.num_patient_requires_bed += 1
       
        #Request a bed for the patient
        req= self.bed.request()
        yield req # Waiit for a bed
        self.occupied_beds += 1
        wait_time = self.env.now - arrival_time
        self.patient_total_wait_time.append(wait_time)
        if wait_time > 0:
            self.patient_who_waited.append(wait_time)
            self.track_waiting_time_for_bed.append(wait_time)
        with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID} was  assigned to a bed at {self.sim_format_time(self.env.now)}"+ '\n')
        
        yield self.env.process(self.patient_gets_doctor(patient_ID))              

        #occupied_beds = self.bed.capacity - len(self.bed.queue)
        #self.track_bed_usage.append((self.env.now,occupied_beds))
        
        #Stimulate the length of stay (LOS) in the bed
        los = random.randint(30,120)
        yield self.env.timeout(self.length_of_stay)
        self.update_last_patient_time()
        with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID} has left the bed at {self.sim_format_time(self.env.now)}"+ '\n')

        self.occupied_beds-= 1
        self.bed.release(req)
        self.update_bed_occupancy()

        
        #This tracks when the user leaves the bed 
        #occupied_beds = self.bed.capacity - len(self.bed.queue)
        #self.track_bed_usage.append((self.env.now, occupied_beds))
        self.update_bed_occupancy()

        self.patient_LOS.append(los)


    def patient_request_doctor_for_doctor_consultation(self,patient_ID,priority):
         arrival_time = self.env.now
         if (priority > 0):
            #Request a doctor for consulation
            req = self.doctor.request(priority= priority)
            yield req # Wait for the doctor to be avavaible 

            wait_time = self.env.now - arrival_time
            self.patient_total_wait_time.append(wait_time)
            if wait_time > 0:
                self.patient_who_waited.append(wait_time)
                self.track_waiting_time_for_doctor.append(wait_time)
          
            with open("patient_log.txt", "a") as output:
                output.write(f"Patient {patient_ID} was assigned to a Doctor at {self.sim_format_time(self.env.now)}" + '\n')
        
            #Stimulate the doctor consultation process 
            #yield self.env.timeout(random.randint(1,5))
            yield self.env.timeout(self.doctor_consultation_duration)
            with open("patient_log.txt", "a") as output:
                output.write(f"Patient {patient_ID}'s Doctor Consultation was completed at {self.sim_format_time(self.env.now)}"+ '\n')
            finish_time = self.env.now
            duration = finish_time - arrival_time
            self.track_time_doctor_consultation.append(duration)
            
            total = probability_discharge + probability_tests + probablity_medication
            
            if total ==0:
                probability_discharge = 1/3
                probability_tests = 1/3
                probablity_medication = 1/3

            
            if total != 1:
                probability_discharge /= total
                probablity_target /= total
                probablity_medication /= total
            
            
            #decision =random.uniform(0,1)
            decision = random.choices(["Discharge", "Tests", "Medication"], weights = [probability_discharge, probability_tests, probablity_medication][0])
            
            if decision == "Discharge":
                self.track_time_for_discharge.append(duration)
                self.update_last_patient_time()
                with open("patient_log.txt", "a") as output:
                    output.write(f"Patient {patient_ID} is discharged at {self.sim_format_time(self.env.now)}"+ '\n')
                self.num_patient_discharged += 1
                

                 #Release the doctor
                self.doctor.release(req)
                with open("patient_log.txt", "a") as output:
                    output.write(f"Patient {patient_ID}'s Doctor released at {self.sim_format_time(self.env.now)}"+ '\n')
            elif decision == "Tests":
               self.num_patient_requires_tests += 1
               with open("patient_log.txt", "a") as output:
                output.write(f"Patient {patient_ID} needs to do tests"+ '\n')
               #Release the doctor
               self.doctor.release(req)
               with open("patient_log.txt", "a") as output:
                output.write(f"Patient {patient_ID}'s Doctor released at {self.sim_format_time(self.env.now)}"+ '\n')
               yield self.env.process(self.patient_request_tests(patient_ID,priority))
              
            else:
              self.num_patient_requires_medication += 1
              with open("patient_log.txt", "a") as output:
                output.write(f"Patient {patient_ID} needs to take medication"+ '\n')
              #Release the doctor
              self.doctor.release(req)
              with open("patient_log.txt", "a") as output:
                output.write(f"Patient {patient_ID}'s Doctor released at {self.sim_format_time(self.env.now)}"+ '\n')
              yield self.env.process(self.patient_request_medication(patient_ID,priority))
         
     
    def patient_request_tests(self,patient_ID, priority):
     arrival_time = self.env.now
     req = self.nurse.request(priority= priority )
     yield req

     wait_time = self.env.now - arrival_time
     self.patient_total_wait_time.append(wait_time)
     if wait_time > 0:
            self.patient_who_waited.append(wait_time)
            self.track_waiting_time_for_nurse.append(wait_time)

     with open("patient_log.txt", "a") as output:
        output.write(f"Patient {patient_ID} was assigned to a Nurse at {self.sim_format_time(self.env.now)}"+ '\n')
     #yield self.env.timeout(random.randint(1,5))
     yield self.env.timeout(self.test_duration)
     
     finish_time = self.env.now
     duration = finish_time - arrival_time
     self.track_time_tests.append(duration)
    
     with open("patient_log.txt", "a") as output:
        output.write(f"Patient {patient_ID} 's tests completed at {self.sim_format_time(self.env.now)}"+ '\n')
     self.nurse.release(req)
     with open("patient_log.txt", "a") as output:   
        output.write(f"Patient {patient_ID}'s Nurse released at {self.sim_format_time(self.env.now)}"+ '\n')
     yield self.env.process(self.patient_request_doctor_follow_up(patient_ID, priority))

     

    def patient_request_medication(self,patient_ID,priority):
        arrival_time = self.env.now
        req = self.nurse.request(priority= priority )
        yield req
        with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID} with priority {priority} was assigned to  a Nurse at {self.sim_format_time(self.env.now)}"+ '\n')
        wait_time = self.env.now - arrival_time
        self.patient_total_wait_time.append(wait_time)
        if wait_time > 0:
            self.patient_who_waited.append(wait_time)
            self.track_waiting_time_for_nurse.append(wait_time)
        with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID} was assigned to a Nurse at {self.sim_format_time(self.env.now)}"+ '\n')
        #yield self.env.timeout(random.randint(1,5))
        yield self.env.timeout(self.medication_duration)
        with open("patient_log.txt", "a") as output:
            output.write(f"Pateint {patient_ID} finished medication at {self.sim_format_time(self.env.now)}" + '\n')
        
        finish_time = self.env.now
        duration = finish_time - arrival_time
        #print(f"Duration " + duration)
        self.track_time_medication.append(duration)
        with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID}'s medication completed at {self.sim_format_time(self.env.now)}"+ '\n')
        self.nurse.release(req)
        with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID}'s Nurse released at {self.sim_format_time(self.env.now)}"+ '\n')
        yield self.env.process(self.patient_request_doctor_follow_up(patient_ID, priority))


    def patient_request_doctor_follow_up(self,patient_ID,priority):
        arrival_time = self.env.now
        
        req= self.doctor.request(priority= priority)
        yield req
        
        wait_time = self.env.now - arrival_time
        self.patient_total_wait_time.append(wait_time)
        if wait_time > 0:
            self.patient_who_waited.append(wait_time)
            self.track_waiting_time_for_doctor.append(wait_time)
        with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID} was assigned to a Doctor for a follow up at {self.sim_format_time(self.env.now)}"+ '\n')
        #yield self.env.timeout(random.randint(1,5))
        yield self.env.timeout(self.follow_up_duration)
        finish_time = self.env.now
        duration = finish_time - arrival_time
        self.track_time_for_follow_up.append(duration)

        with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID}'s Doctor follow up completed at {self.sim_format_time(self.env.now)}"+ '\n')
    
        self.update_last_patient_time()
        with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID} has left the A&E at {self.sim_format_time(self.env.now)}"+ '\n') 
        
        self.doctor.release(req)
        with open("patient_log.txt", "a") as output:
            output.write(f"Patient {patient_ID}'s Doctor released at {self.sim_format_time(self.env.now)}"+ '\n')

# FROM HERE CODE IS FOR DISPLAYING THE SIMULATION 

st.set_page_config(page_title="A&E Simulation🏥", layout="wide")

#st.title("A&E Simulation")
st.markdown("<h1 style = 'text-align: center; color: white;'>A&E Simulation🏥</h1>", unsafe_allow_html=True)
#st.write("Testing")

with st.sidebar:
    st.header("⚙️Simulation Configuration")

    with st.expander(label="Resources Allocation", expanded=False):
        num_clerks = st.slider(" 👩‍💼Number of Clerks", 1, 10, 3)
        num_nurses = st.slider("👩‍⚕️Number of Nurses", 1, 20, 10)
        num_doctors = st.slider("👨‍⚕️Number of Doctors", 1, 20, 10)
        num_beds = st.slider("🛏️Number of Beds", 1, 20, 5)
        mean_interarrival_time = st.slider("🚶‍♀️‍➡️Mean Arrival Time", 1, 10,3 )
        simulation_run_time= st.number_input("🕛Simulation Run Time in minutes", 1, 1440, 100)    
    
    with st.expander(label = "Triage Allocation", expanded = False):
        num_immediate = st.number_input("🔴 % of Immediate Patients", 0, 100, 1)
        num_very_urgent = st.number_input(" % of Very Urgent Patients", 0, 100,1)
        num_urgent = st.number_input("🟡 % of Urgent Patients", 0, 100, 1)
        num_standard = st.number_input("🟢 % of Standard Patients", 0,100,1)
        num_non_urgent = st.number_input("🔵 % of Non-Urgent Patients", 0, 100, 1)
    
    with st.expander(label = "Patient Flow", expanded= False):
        admission_duration = st.slider("Admission Duration", 1, 10, 5)
        risk_assessment_duration = st.slider("Risk Assesmet Duration", 1, 10, 5)
        doctor_consultation_duration = st.slider("Doctor Consultation Duration", 1, 10, 5)
        test_duration= st.slider(" Test Duration", 1, 10, 5)
        medication_duration = st.slider("Medication Duration", 1, 10, 5)
        follow_up_duration = st.slider("Follow Up Duration", 1, 10, 5)
        length_of_stay = st.slider("Length of Stay", 1, 10, 5)

        probablility_discharge = st.slider("Probability of Discharge", 0.0, 1.0, 0.5)
        probability_tests = st.slider("Probability of Tests", 0.0, 1.0, 0.9)
        probablity_medication = st.slider("Probability of Medication", 0.0, 1.0,)
        
    run_button_pressed = False # Initial Value      
    if st.button("▶️ Run Simulation"):
       run_button_pressed = True

with st.expander(label = "About", expanded = False):
    st.write("Need To Writte")
   
if run_button_pressed:

        if "patient_log_data" in st.session_state:
            del st.session_state.patient_log_data

        #This clears the contents of the patient log file from previous runs
        with open("patient_log.txt", "w") as output:
            output.write('')
        
        #Creates the simulation environmnment (A&E)
        env = sp.Environment()

        # Create the A&E department with resources
        a_and_e = AnE(env, num_doctors, num_nurses, num_beds, num_clerks, 
                      num_immediate, num_very_urgent, num_urgent, num_standard, num_non_urgent,
                      admission_duration, risk_assessment_duration, doctor_consultation_duration, test_duration, medication_duration, follow_up_duration, length_of_stay,
                      probablility_discharge, probability_tests, probablity_medication
                                            
                      )
        env.process(a_and_e.patient_generator(mean_interarrival_time,simulation_run_time))
        with st.spinner("Running Simulation"):
        
            env.run(simulation_run_time) #This runs for how long minutes the user wants
        #while env.peek() < until:
            #env.step()
            while a_and_e.active_patients != set():
                env.step()

        #while any( resource.users for resource in [a_and_e.doctor, a_and_e.nurse, a_and_e.bed, a_and_e.clerk]):
            #env.step()
        #while env.peek() < float("inf") and any(resource.users for resource in [a_and_e.doctor, a_and_e.nurse, a_and_e.clerk, a_and_e.bed]):
            #env.step()
        #This to test if the  last patient has been processed fully 
        #print(f"Last patient {a_and_e.patientCount} left at {a_and_e.sim_format_time(a_and_e.last_patient_time)}")

        st.success(" ✅ Simulation Completed")
        simulation_completed = True
    # Display the results
        
        with st.spinner("Gathering Results"):
            st.subheader("Simulation Results")
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric(label = "Total Patients Seen", value = a_and_e.patientCount)
            #st.write(f"Total patients seen: {a_and_e.patientCount}")
            

            ######################################################
            #Debugging purposes checking unfinished patients
            #print("Checking for unfished patients")
            #for resource in [a_and_e.doctor, a_and_e.nurse, a_and_e.bed, a_and_e.clerk]:
                #if resource.users:
                #     print (f"Resource {resource} has unfinished patients  {[user for user in resource.users]}")
                #else:
                #    print(f"Resource {resource} has no unfinished patients")
            #####################################################
            #This calculates the average waiting time for patients who had to wait
            #print(a_and_e.patient_total_wait_time) Testing 

            with col2:
                if len(a_and_e.patient_who_waited) == 0:
                    average_wait_time = sum(a_and_e.patient_who_waited) / len(a_and_e.patient_who_waited)
                else:
                    average_wait_time = 0 

                hours = int(average_wait_time // 60)
                minutes = int(average_wait_time % 60)
                st.metric(label= "The average for patients who had to had wait time is ", value = (f"{hours} hours and {minutes} minutes"))

            #This calculates the overall average wait time even with pateints who did not wait 
            overall_average_time = sum(a_and_e.patient_total_wait_time) / len (a_and_e.patient_total_wait_time)

            hours1= int(overall_average_time // 60)
            minutes1= int(overall_average_time % 60)
            
            with col1:
                st.metric(label= " Overall Average Wait Time" , value= (f"{hours1} hours and {minutes1} minutes"))


            with col2:
                st.subheader("Patient Log")
                try:
                    with open("patient_log.txt", "r", encoding="utf-8") as file:
                        log_data = file.read()
                        st.session_state.patient_log_data = log_data  # Store in session state

                except FileNotFoundError:
                    st.session_state.patient_log_data = None  # Handle missing file

                # Display the updated log
                if st.session_state.patient_log_data:

                    with st.container(height = 300):
                        log_entries = st.session_state.patient_log_data.split("\n")  # Ensure each log is separate
                        formatted_text = "<br>".join(log_entries)  # Join them with HTML line breaks
                        st.markdown(formatted_text, unsafe_allow_html=True)

                    st.download_button(label="Download Patient Log", data=st.session_state.patient_log_data.encode("utf-8"), file_name="patient_log.txt", mime="text/plain")
                else:
                    st.warning(" No patient log available.")



            st.subheader(" 📊Visualisations")

            with st.expander("Bed Occupancy Over Time",expanded=True):
                    #print(a_and_e.track_bed_usage) Testing 
                    times,bed_count = zip(*a_and_e.track_bed_usage) # This  unpacks into two lists time and bed count 
                    #This graph is for bed occupancy over time 
                    fig, ax = plt.subplots(figsize=(10,5))
                    ax.scatter(times, bed_count, marker= "x", color = "red")
                    ax.set_xlabel("Simulation Time (minutes)")
                    ax.set_ylabel("Occupied Beds")
                    ax.set_title("Bed Occupancy Over Time")
                    ax.grid()
                    ax.set_xlim(0,simulation_run_time + 100)
                    ax.set_ylim(0,a_and_e.bed.capacity)
                    st.pyplot(fig)

            # Length of stay for patients 
            with st.expander("Length of Stay for Patients Occupued in Bed", expanded=True):
                    fig12, ax = plt.subplots(figsize=(10,5))
                    ax.boxplot(a_and_e.patient_LOS, vert=False, patch_artist=True, boxprops=dict(facecolor = "purple"))
                    ax.set_title("Length of Stay for Patients occupied in bed")
                    ax.set_xlabel("Length of stay (minutes)")
                    ax.grid()
                    st.pyplot(fig12)

            #This graph is for the time pateints spent in the AnE
            with st.expander("Time Patients Spent in A&E", expanded=True):
                col1, col2, col3 = st.columns(3)

                with col1:
                    fig1, ax = plt.subplots(figsize=(10,5))
                    ax.boxplot(a_and_e.patient_spent_time, vert=False, patch_artist = True, boxprops=dict(facecolor="red"))#, flierprops=dict(marker="D", color = "blue", markersize = 8))
                    ax.set_title("Time Pateints Spent in A&E")
                    ax.set_xlabel("Time Patient Spent in A&E (minutes)")
                    ax.grid()
                    st.pyplot(fig1)
                with col2:
                    #This graph is for the time patients spent in the AnE
                    fig2, ax = plt.subplots(figsize=(10,5))
                    sns.violinplot(a_and_e.patient_spent_time, color = "red", inner = "quartile", cut = 0)
                    ax.set_title("Time Patients Spent in A&E")
                    ax.set_xlabel("Time Patient Spent in A&E (minutes)")
                    ax.set_ylim(0, max(a_and_e.patient_spent_time) + 100)
                    st.pyplot(fig2)

            #Histogram for patient spent time 
                with col3:
                    fig3, ax = plt.subplots(figsize=(10,5))
                    number_of_bins = int(np.sqrt(len(a_and_e.patient_spent_time)))
                    ax.hist(a_and_e.patient_spent_time, bins=number_of_bins, color="red", edgecolor="black")
                    ax.set_title("Time Patients Spent in A&E")
                    ax.set_xlabel("Time Patient Spent in A&E (minutes)")
                    ax.set_ylabel("Frequency")
                    ax.grid(axis = "y")
                    st.pyplot(fig3)

            #This graph is for the average waiting time for patients
            with st.expander("Patient Wait Time", expanded = True):
                col1, col2 = st.columns(2)
                
                with col1:
                    fig4, ax = plt.subplots(figsize=(10,5))
                    number_of_bins1 = int(np.sqrt(len(a_and_e.patient_who_waited)))
                    ax.hist(a_and_e.patient_who_waited, bins=number_of_bins1, color="blue", edgecolor="black")
                    ax.set_title("Wait Time for Patients")
                    ax.set_xlabel("Wait Time (minutes)")
                    ax.set_ylabel("Frequency")
                    ax.grid()
                    ax.set_xlim(0, max(a_and_e.patient_who_waited)+ 100)
                    st.pyplot(fig4)

                with col2:

                    fig5, ax = plt.subplots(figsize=(10,5))
                    ax.boxplot(a_and_e.patient_who_waited , vert=False, patch_artist=True, boxprops=dict(facecolor="blue"))
                    ax.set_title("Wait Time for Patients")
                    ax.set_xlabel("Wait Time (minutes)")
                    ax.set_xlim(0, max(a_and_e.patient_who_waited)+ 40)
                    ax.grid()
                    st.pyplot(fig5)

            # Average wait times for the resources 
            
            
            with st.expander("Resource Wait Times", expanded = True):
                col1, col2 = st.columns(2)
                with col1:
                        
                    average_resource_wait_time = [ np.mean(a_and_e.track_waiting_time_for_clerk),
                                                np.mean(a_and_e.track_waiting_time_for_nurse),
                                                np.mean(a_and_e.track_waiting_time_for_doctor),
                                                np.mean(a_and_e.track_waiting_time_for_bed)
                                                ]
                    resource_names = ["Clerk", "Nurse", "Doctor", "Bed"]
                    fig6, ax = plt.subplots(figsize=(10,5))
                    ax.bar(resource_names, average_resource_wait_time, color = "green" )
                    ax.set_title("Average Wait Time for Resoruces")
                    ax.set_xlabel("Resources")
                    ax.set_ylabel("Average Wait Time Minutes")
                    max_y_time = max(average_resource_wait_time)
                    ax.set_ylim(0, max_y_time + 10)
                    ax.set_yticks(range(0, int(max_y_time)+ 50, 100)) # Goes up by every 50 minutes the ticks 

                    ax.grid(axis="y")
                    st.pyplot(fig6)
            
                #Total wait time for the resources
                with col2:
                    resource_wait_time = [ sum(a_and_e.track_waiting_time_for_clerk),
                                        sum(a_and_e.track_waiting_time_for_nurse),
                                        sum(a_and_e.track_waiting_time_for_doctor),
                                        sum(a_and_e.track_waiting_time_for_bed)
                                    ]   
                    max_y_time_axis = max(resource_wait_time)
                    fig7, ax = plt.subplots(figsize=(10,5))
                    ax.bar(resource_names, resource_wait_time, color = "green" )
                    ax.set_title(" Wait Time for Resources")
                    ax.set_xlabel("Resources")
                    ax.set_ylabel("Wait Time (Minutes)")
                    ax.set_ylim(0, max_y_time_axis + 100) 
                    ax.set_yticks(range(0, int(max_y_time_axis)+100, 200))
                    ax.grid(axis="y")
                    st.pyplot(fig7)    

            #Triage patients bar chart
            with st.expander("Triage Categories", expanded = True):

                max_y = (a_and_e.patientCount// 10 + 1) * 10 # Rounds up to the nearest 10
                triage_categories = ["Immediate", "Very Urgent", "Urgent", "Standard", "Non-Urgent"]
                fig8, ax = plt.subplots(figsize=(10,5)) 
            
            
            
                ax.bar(triage_categories, [a_and_e.num_patient_immediate, a_and_e.num_patient_very_urgent, a_and_e.num_patient_urgent, a_and_e.num_patient_standard, a_and_e.num_patient_non_urgent], color="purple")
                ax.set_title("Number of Patients in Triage Categories")
                ax.set_ylabel("Number of Patients")
                ax.set_xlabel("Triage Categories")
                ax.grid(axis='y')
                ax.set_yticks(range(0, max_y+ 1,50)) #Added +1 as rangee excludes the last number, the y scales goes up by 10
                st.pyplot(fig8)

            #Duration for the stages of the patient flow
            with st.expander("Patient Flows", expanded = True):
                col1, col2 = st.columns(2)
            
                with col1:
                    average_time_for_stages = [np.mean(a_and_e.track_time_admission),
                                            np.mean(a_and_e.track_time_risk_assessment),
                                            np.mean(a_and_e.track_time_doctor_consultation),
                                            np.mean(a_and_e.track_time_tests),
                                            np.mean(a_and_e.track_time_medication),
                                            np.mean(a_and_e.track_time_for_follow_up),
                                            np.mean(a_and_e.track_time_for_discharge)]
                    stage_names = ["Admission", "Risk Assessment", "Doctor Consultation", "Tests", "Medication", "Follow Up", "Discharge"]
                    
                    fig9, ax = plt.subplots(figsize=(13,5))
                    ax.bar(stage_names, average_time_for_stages, color="orange")
                    ax.set_title("Average Time for Stages of Patient Flow")
                    ax.set_xlabel("Stages")
                    ax.set_ylabel("Average Time (minutes)")
                    ax.grid(axis="y")
                    st.pyplot(fig9)
                
                with col2:


                    #Number of patients in different stages of the process
                    stage_names = ["Discharged", "Requires Tests", "Requires Medication", "Requires Bed"]
                    fig11, ax = plt.subplots(figsize=(10,5))
                    ax.bar(stage_names, [a_and_e.num_patient_discharged, a_and_e.num_patient_requires_tests, a_and_e.num_patient_requires_medication, a_and_e.num_patient_requires_bed], color="orange")
                    ax.set_title("Number of Patients in Different Stages of the Process")
                    ax.set_xlabel("Stages")
                    ax.set_ylabel("Number of Patients")
                    ax.grid(axis="y")
                    st.pyplot(fig11)

            with st.expander("Resource Utilisation", expanded = True):
                #Resource utilisation
                resource_utilisation = [a_and_e.doctor.count / a_and_e.doctor.capacity,
                                        a_and_e.nurse.count / a_and_e.nurse.capacity,
                                        a_and_e.bed.count / a_and_e.bed.capacity,
                                        a_and_e.clerk.count / a_and_e.clerk.capacity]
                fig10, ax = plt.subplots(figsize=(10,5))
                ax.bar(resource_names, resource_utilisation, color = "purple")
                ax.set_title("Resource Utilisation")
                ax.set_xlabel("Resource Type")
                ax.set_ylabel("Utilisation Rate")
                ax.grid(axis="y")
                st.pyplot(fig10)

    
        