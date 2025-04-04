import simpy as sp
import random
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import seaborn as sns 
import streamlit as st

import plotly.express as px
import plotly.graph_objects as go


#Creates the simulation environment 
class AnE:
    
    def __init__(self, env, num_doctors, num_nurses, num_beds, num_clerk,
                 num_immediate, num_very_urgent, num_urgent, num_standard, num_non_urgent,
                 admission_duration, risk_assessment_duration, doctor_consultation_duration, test_duration, medication_duration, follow_up_duration, length_of_stay,
                 probability_discharge, probability_tests, probability_medication,
                 start_time
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
        self.percentage_discharge = probability_discharge
        self.percentage_tests = probability_tests
        self.percentage_medication = probability_medication
       
       
        #self.patient_id=0
        self.patientCount = 0 
        self.active_patients = set()

        self.occupied_beds = 0 #Will increment and decrement 
        self.last_patient_time=0
        #self.priority = 0


        self.start_time = start_time
       
        self.track_bed_usage = [] # This tracks occupied bed over time 
        self.patient_LOS=[] # Length of stay for the patient if they are admitted to a bed
       
        self.patient_spent_time = [] # List the time the patient spent in the A&E


        self.patient_who_waited = [] #List all the wait times for patients who waited
        self.patient_total_wait_time = [] # Total wait times for all the patients
        
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

        #Total simulation run time
        self.total_simulation_time = 0 

        # Resources Utilisation tracking
        self.track_clerk_utilisation = []
        self.track_nurse_utilisation = []
        self.track_doctor_utilisation = []
        self.track_bed_utilisation = []
        

        



    def sim_format_time(self,time):
         current_time = (datetime.combine(datetime.today(), self.start_time) + timedelta(minutes=time)).time()
         return current_time.strftime("%H:%M") # This formats the time as hour:minute
    

    def format_in_hours_and_minutes(self, time):
        minutes = time / 60
        return f"{int(minutes) //60}h {int(minutes % 60)}m "

    def update_last_patient_time(self):
        self.last_patient_time = max(self.env.now, self.last_patient_time)
    
    #patient is the process
    def patient_generator(self, mean_interarrival_time, finish_time):
        patient_ID = 0
        self.update_bed_occupancy()
        while True:
                interarrival_time= np.random.exponential(mean_interarrival_time)
                yield self.env.timeout(interarrival_time) 
                
                if self.env.now > finish_time:
                    break 
                #number_of_patients_arrival = np.random.poisson(average_rate_patients_per_interval)  # the poisson takens in the average rate of patients arriving per interval time
                #for _ in range(number_of_patients_arrival):
                self.patientCount +=1 
                patient_ID+=1
                self.active_patients.add(patient_ID)
                    
                with open("patient_log.txt", "a") as output:
                    output.write(f"Patient {patient_ID} arrived at {self.sim_format_time(self.env.now)}" + '\n')
                    
                #Start patient flow process
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
                        "Red (Immediate)": (self.num_immediate,0), # 5% chance of being immediate with 0 being the highest prirority
                        "Orange (Very Urgent)": (self.num_very_urgent,1), # 10% chance of being very urgent
                        "Yellow (Urgent)": (self.num_urgent,2), #35% chance of being urgent
                        "Green (Standard)": (self.num_standard,3), #30% chance of being standard
                        "Blue (Non-Urgent)": (self.num_non_urgent,4) #20% chance of being non-urgent
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
            yield self.env.timeout(self.risk_assesment_duration)
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
            
            total = self.percentage_discharge + self.percentage_tests + self.percentage_medication
            
            if total ==0:
                self.percentage_discharge = 100/3
                self.percentage_tests = 100/3
                self.percentage_medication = 100/3

            
            if total != 100:
                self.percentage_discharge = (self.percentage_discharge / total) * 100 
                self.percentage_tests = (self.percentage_tests / total) * 100
                self.percentage_medication = (self.percentage_medication / total) * 100
            
            
            #decision =random.uniform(0,1)
            decision = random.choices(["Discharge", "Tests", "Medication"], weights = [self.percentage_discharge, self.percentage_tests, self.percentage_medication])[0]
            
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
            output.write(f"Patient {patient_ID} finished medication at {self.sim_format_time(self.env.now)}" + '\n')
        
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
    
    def resource_utilisation_tracker(self):
        while True:
            self.update_resource_utilisation()
            yield self.env.timeout(1)


    def update_resource_utilisation(self):
        self.track_clerk_utilisation.append((self.env.now, len(self.clerk.queue), self.clerk.count))
        self.track_nurse_utilisation.append((self.env.now, len(self.nurse.queue), self.nurse.count))
        self.track_bed_utilisation.append((self.env.now, len(self.bed.queue), self.bed.count))
        self.track_doctor_utilisation.append((self.env.now, len(self.doctor.queue), self.doctor.count))

    def caculate_resource_utilisation(self, resource_track, resource_capacity, last_patient_time):
        total_usage_time = 0
        for i in range(len(resource_track) - 1):
            time_interval = resource_track[i + 1][0] - resource_track[i][0]  # Time difference
            usage = resource_track[i][2]  
            total_usage_time += usage * time_interval  

        utilisation_percentage = (total_usage_time / (last_patient_time * resource_capacity)) * 100
        
        # Ensure utilization is at most 100%
        return min(utilisation_percentage,100)  
    
# FROM HERE CODE IS FOR DISPLAYING THE SIMULATION 

st.set_page_config(page_title="A&E Simulation🏥", layout="wide")

#st.title("A&E Simulation")
st.markdown("<p style =  'font-size:55px; font-weight:bold; text-align: center;'>A&E Simulation🏥</p>", unsafe_allow_html=True)
#st.write("Testing")

with st.sidebar:
    st.markdown("⚙️ <span style = 'font-size: 25px;'>Simulation Configuration</span>", unsafe_allow_html=True)

    with st.expander(label="Resources Allocation", expanded=False):
        st.markdown("<span style = 'font-size: 20px;'> Configure the number of resources in the A&E department </span>", unsafe_allow_html=True)
        
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 👩‍💼Number of Clerks:</p>", unsafe_allow_html= True)
        num_clerks = st.slider("", 1, 10, 3)
        st.markdown("<p style='font-size:20px; font-weight:bold;'>👩‍⚕️Number of Nurses:</p>", unsafe_allow_html= True)
        num_nurses = st.slider("", 1, 20, 10)
        st.markdown("<p style='font-size:20px; font-weight:bold;'>👨‍⚕️Number of Doctors:</p>", unsafe_allow_html= True)
        num_doctors = st.slider(" ", 1, 20, 10)
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🛏️Number of Beds:</p>", unsafe_allow_html= True)
        num_beds = st.slider("  ", 1, 20, 5)
    
    with st.expander(label = "Triage Allocation", expanded = False):
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🔴 % of Immediate Patients:</p>", unsafe_allow_html= True)
        num_immediate = st.number_input( "🔴",0, 100, 1)
        
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🟠 % of Very Urgent Patients:</p>", unsafe_allow_html= True)
        num_very_urgent = st.number_input("🟠", 0, 100,1)
        
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🟡 % of Urgent Patients:</p>", unsafe_allow_html= True)
        num_urgent = st.number_input( "🟡", 0, 100, 1)
        
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🟢 % of Standard Patients:</p>", unsafe_allow_html= True)
        num_standard = st.number_input("🟢",0,100,1)
        
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🔵 % of Non-Urgent Patients:</p>", unsafe_allow_html= True)
        num_non_urgent = st.number_input("🔵",0, 100, 1)

        	
         # Validate that the sum of percentages equals 100
        total_percentages = num_immediate + num_very_urgent + num_urgent + num_standard + num_non_urgent
        if total_percentages != 100:
            st.warning(f"The total percentage of triage categories is {total_percentages}%. Please ensure it equals 100%.")

    
    with st.expander(label = "Patient Flow", expanded= False):
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🔁Admission Duration:</p>", unsafe_allow_html= True)
        admission_duration = st.slider("", 1, 10, 5)
       
        st.markdown("<p style='font-size:20px; font-weight:bold;'> ⚠️Risk Assesment Duration:</p>", unsafe_allow_html= True)

        risk_assessment_duration = st.slider(" ", 1, 10, 5)
        
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🩺Doctor Consultation:</p>", unsafe_allow_html= True)
        doctor_consultation_duration = st.slider("                          ", 1, 10, 5)
        
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🧪Test Duration:</p>", unsafe_allow_html= True)
        test_duration= st.slider("  ", 1, 10, 5)
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 💊 Medication Duration</p>", unsafe_allow_html= True)
        medication_duration = st.slider("                    ", 1, 10, 5)
        
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 👩‍💼Doctor Follow Up Duration:</p>", unsafe_allow_html= True)
        follow_up_duration = st.slider("    ", 1, 10, 5)
        
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🏥Length of Stay:</p>", unsafe_allow_html= True)
        length_of_stay = st.slider("     ", 1, 10, 5)

        st.markdown("<p style='font-size:20px; font-weight:bold;'>📤 Percentage of Discharg:e</p>", unsafe_allow_html= True)
        percentage_discharge = st.slider("      ", 0, 100, 1)
       
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🧬 Percentage of Tests:</p>", unsafe_allow_html= True)
        percentage_tests = st.slider("           ", 0, 100, 1)
       
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 💉Percentage of Medication:</p>", unsafe_allow_html= True)
        percentage_medication = st.slider("             ",0, 100, 1)

        # Validate that the sum of percentages equals 100 
        total_percentage = percentage_discharge + percentage_tests + percentage_medication
        if total_percentage != 100:
            st.warning(f"The total percentage of patient flow categories is {total_percentage}%. Please ensure it equals 100%.")
        
    
    with st.expander(label = " Patient Generator", expanded = False):
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🚶‍♀️‍➡️Mean Arrival Time:</p>", unsafe_allow_html= True)
        mean_interarrival_time = st.slider("                                                                         ", 1, 10,3 )
        #average_rate_patients_per_interval = st.slider(" 🚶‍♂️‍➡️Average Rate of Patients per Interval", 1, 50, 10)



    with st.expander(label = "Simulation Configuration", expanded = False):
        st.markdown("<p style='font-size:20px; font-weight:bold;'> 🕛Simulation Run Time in minutes</p>", unsafe_allow_html= True)

        simulation_run_time= st.number_input("                                          ", 1, 1440, 100)
        
        st.markdown("<p style='font-size:20px; font-weight:bold;'>⏳ Start Time:</p>", unsafe_allow_html= True)
        start_time = st.time_input("                                                               ", datetime(2025, 3, 15, 8, 0).time())





    run_button_pressed = False # Initial Value      
    if st.button("▶️ Run Simulation"):
       if (total_percentage + total_percentages !=200):
           if total_percentages != 100:
                st.error("Please check the triage percentages. They need to add up to 100%")
           if total_percentage !=100:
               st.error("Please check the patient flow percentages. They need to add up to 100%")

       else:
           run_button_pressed = True

with st.expander(label = "About", expanded = False):
    st.subheader("About the A&E Simulation", anchor = False)
    st.write("This Simulation is a descrete event simulation that is designed  through a python framework called Simpy, to model and analyse patient flow, resource utilisation and effieceny within an Accident & Emergency deparment.")
    st.write("The simulation enables you to configure key hospital parameters located at the left side-panel under **⚙️ Simulation Configuration**. It includes resource allocation of staffing levels,  triage allocation, and process durations ( e.g., how long  risk assesment addmission takes) and the timings. These are here to observe  how these paramters affect patient flow and assist you on your decision based on the analysis provided by the simulation results.")
    st.subheader("Simulation Configuration Explained", anchor = False)
   
    st.markdown("<p style='font-size:22px; font-weight:bold;'> 1. Resource Allocation</p>", unsafe_allow_html = True)
    st.write("This section allows you to configure the number of healthcare proffesionals and beds available. These are known as **Resources** in the simulation. Resources are the entities that are used to process patients. Proper resource management is crucial for patient flow and reducing waiting times.")
    st.write(" - **👩‍💼 Number of Clerks**:  Clerks handles patient registration and administrative tasks" )
    st.write(" - **👩‍⚕️ Number of Nurses**: Nurses conducts initatial assesments and triage patients")
    st.write(" - **👨‍⚕️ Number of Doctors**: Doctors provides consultations and treatments.")
    st.write(" - **🛏️ Number of Beds**:  Beds are used to accomodate patients who require furthur treatment or observation ")
    
    st.markdown("<p style='font-size:22px; font-weight:bold;'> 2. Triage Allocation</p>", unsafe_allow_html = True)
    st.write("Patients are categorised based on their urgency and severity of their condition. This is known as Triage. The triage system used in this simulation is the **Manchester Triage**, which classifies patients into five categoires which affects the order in which they recieve treatment. The triage needs to add up to **100%**.")
    st.write(" - **🔴 Immediate Patients (%)**: Life-threatning conditions")
    st.write(" - **🟠 Very Urgent Patients(%)**: Sever but non-life threatening")
    st.write(" - **🟡 Urgent Patients (%)**: Moderate conditions requring prompt care ")
    st.write(" - **🟢 Standard Patients (%)**:  Less critical but need attention")
    st.write(" - **🔵 Non-Urgent Patients (%)**: Low-risk cases")

    st.markdown("<p style='font-size:22px; font-weight:bold;'> 3. Patient Flow</p>", unsafe_allow_html = True)
    st.write("- **🔁Admission Duration**: Time taken by the clerk to register a patient")
    st.write("- **⚠️ Risk Assesment Duration**: Time taken by nurses to assess and triage a patient")
    st.write("- **🩺 Doctor Consultation Duration**: Time taken by doctor to peform a consultation to a patient")
    st.write("- **🧪 Test Duration**: Time required for lab tests")
    st.write("- **💊 Medication Duration**: Time required for the medication process")
    st.write("- **👩‍💼 Doctor Follow Up Duration**: A follow up consultation conducted by a doctor after a treatment ")
    st.write("- **🏥 Length of Stay**: Time spent in bed")
    st.write("The likelyhood of a patient to be discharged, require tests or medication. The percentages need to add up to **100%**.")
    st.write("- **📤 Percentage of Discharge:**: Patients who leave A&E without anymore check-ups")
    st.write("- **🧬 Percentage of Tests**: Patients requiring diagnostic tests")
    st.write("- **💉 Percentage of Medication**: Patients needing medication for treatment")

    st.markdown("<p style='font-size:22px; font-weight:bold;'> 4. Patient Generator</p>", unsafe_allow_html = True)
    st.write("This section allows you to control how frequently new patients arrive at the A&E department. The **Mean Arrival Time** is the average time between patient arrivals. A lower value means more frequent arrivals, while a higher value means less frequent arrivals. This was done through exponential to make it random as possible." )
    st.write( " - **🚶‍♀️‍➡️Mean Arrival Time**:  How much patient arrives")
    st
    
    
    st.markdown("<p style='font-size:22px; font-weight:bold;'> 5. Time Configuration</p>", unsafe_allow_html = True)
    st.write("- **🕛Simulation Run Time in Minutes**: The total duration of the simulation in minutes. But note the simulation time might exceed when all patients have been processed")
    st.write("- **⏳Start Time**: The time of the day the simulation begins")

    st.markdown("<p style='font-size:22px; font-weight:bold;'> Once all are entered press the run simulation button to start the simulation</p>", unsafe_allow_html = True)



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
                      percentage_discharge, percentage_tests, percentage_medication,
                      start_time
                                            
                      )
        env.process(a_and_e.patient_generator(mean_interarrival_time,simulation_run_time))
        env.process(a_and_e.resource_utilisation_tracker())
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
            st.header("Simulation Results", anchor = False, divider = "green")
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
            st.write(a_and_e.last_patient_time)
            with col2:
                if len(a_and_e.patient_who_waited) > 0:
                    average_wait_time = sum(a_and_e.patient_who_waited) / len(a_and_e.patient_who_waited)
                else:
                    average_wait_time = 0 

                if  average_wait_time != 0:
                    hours = int(average_wait_time // 60)
                    minutes = int(average_wait_time % 60)
                    st.metric(label= "The average for patients who had to wait time is ", value = (f"{hours} hours and {minutes} minutes"))
                else:
                    st.metric(label= "The average for patients who had to wait time is ", value = "No patients waited")

            #This calculates the overall average wait time even with patients who did not wait 
            overall_average_time = sum(a_and_e.patient_total_wait_time) / len (a_and_e.patient_total_wait_time)

            hours1= int(overall_average_time // 60)
            minutes1= int(overall_average_time % 60)
            
            with col1:
                st.metric(label= " Overall Average Wait Time" , value= (f"{hours1} hours and {minutes1} minutes"))


            with col2:
                st.subheader("Patient Log", anchor = False, divider = True)
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



            st.subheader(" 📊Visualisations", anchor= False, divider= "red")

            with st.expander("Bed Occupancy Over Time", expanded=True):
                if a_and_e.track_bed_usage:
                    #print(a_and_e.track_bed_usage) Testing 
                    times, bed_count = zip(*a_and_e.track_bed_usage)  # This unpacks into two lists time and bed count 
                    #This graph is for bed occupancy over time 
                    fig1 = px.line(x=times, y=bed_count, labels={"x": "Simulation Time (minutes)", "y": "Occupied Beds"}, title = "Bed Occupancy Over Time", line_shape= "linear")
                    fig1.update_traces(line = dict(color = "purple"))
                    st.plotly_chart(fig1)
                else:
                    st.write("No data")

           
            # Length of stay for patients 
            with st.expander("Length of Stay for Patients Occupued in Bed", expanded=True):
                    fig2 = px.box(x=a_and_e.patient_LOS,title="Length of Stay for Patients ", labels={"x": "Length of Stay (minutes)"})                    
                    st.plotly_chart(fig2)
                  
                  
                  

            #This graph is for the time patients spent in the AnE
            with st.expander("Time Patients Spent in A&E", expanded=True):
                col1, col2, col3 = st.columns(3)

                with col1:
                    if len(a_and_e.patient_spent_time) > 0:
                        fig3 = px.box(x=a_and_e.patient_spent_time, title = " Time Patients Spent in A&E", labels = {"x": "Minutes"})
                        st.plotly_chart(fig3)
                    else:
                        st.write("No Patients spent time in A&E")
                    

                with col2:
                    if len(a_and_e.patient_spent_time) > 0:

                        #This graph is for the time patients spent in the AnE
                        fig4= px.violin(y=a_and_e.patient_spent_time, title = "Time Patients Spent in A&E", labels = {"y": "Minutes"})
                        fig4.update_traces(marker=dict(color = "red"))
                        fig4.update_traces(box_visible=True, meanline_visible=True)
                        st.plotly_chart(fig4)
                    else:    
                        st.write("No patient spent time in A&E")

            #Histogram for patient spent time 
                with col3:
                    fig5 = px.histogram(x= a_and_e.patient_spent_time, nbins=int( np.sqrt(len(a_and_e.patient_spent_time))),title = "Time Patients Spent in A&E", labels = {"x": "Minutes", "y": "Frequency"})
                    fig5.update_traces(marker=dict(color = "#FFA07A",line=dict(color="black", width=1)))
                    st.plotly_chart(fig5)
              
              

            #This graph is for the average waiting time for patients
            with st.expander("Patient Wait Time", expanded = True):
                col1, col2 = st.columns(2)
                
                with col1:

                    if len(a_and_e.patient_who_waited) > 0:
                       fig5 = px.histogram(
                           x=a_and_e.patient_spent_time,
                           nbins=int(np.sqrt(len(a_and_e.patient_who_waited))),
                           title="Wait Time for Patients",
                           labels={"x": "Minutes", "y": "Frequency"}
                       )
                       fig5.update_traces(marker=dict(color="#FDB7EA", line=dict(color="black", width=1)))
                       st.plotly_chart(fig5)
                    else:
                        st.write("No patient wait times.")

                with col2:
                    if len(a_and_e.patient_who_waited) > 0:

                        fig6 = px.box(x = a_and_e.patient_who_waited, title = "Wait Time for Patients", labels = {"x": "Wait Time (minutes)"})
                        st.plotly_chart(fig6)

                    else:
                        st.write("No Patient wait times.")

            # Average wait times for the resources 
            
            
            with st.expander("Resource Wait Times", expanded = True):
                col1, col2 = st.columns(2)
                with col1:
                        
                    average_resource_wait_time = [ np.mean(a_and_e.track_waiting_time_for_clerk) if a_and_e.track_waiting_time_for_clerk else 0,
                                                np.mean(a_and_e.track_waiting_time_for_nurse) if a_and_e.track_waiting_time_for_nurse else 0,
                                                np.mean(a_and_e.track_waiting_time_for_doctor) if a_and_e.track_waiting_time_for_doctor else 0,
                                                np.mean(a_and_e.track_waiting_time_for_bed) if a_and_e.track_waiting_time_for_bed else 0
                                                ]
                    resource_names = ["Clerk", "Nurse", "Doctor", "Bed"]
                    if(len(average_resource_wait_time)> 0):
                        fig7 = px.bar(x = resource_names, y = average_resource_wait_time, title = "Average Wait Time for Resources", labels = {"x": "Resources", "y": "Average Wait Time (Minutes)"})
                        fig7.update_traces(marker=dict(color = "#DAF7A6"))
                        st.plotly_chart(fig7)
                    else:
                        st.write("No wait times for resources.")
                
                #Total wait time for the resources
                with col2:
                    resource_wait_time = [ sum(a_and_e.track_waiting_time_for_clerk),
                                        sum(a_and_e.track_waiting_time_for_nurse),
                                        sum(a_and_e.track_waiting_time_for_doctor),
                                        sum(a_and_e.track_waiting_time_for_bed)
                                    ]   
                    if len(resource_wait_time) > 0: 
                        fig8 = px.bar( x = resource_names, y = resource_wait_time, title = " Total Wait Time for Resources", labels = {"x": "Resources", "y": "Wait Time (Minutes)"}) 
                        fig8.update_traces(marker=dict(color = "#DAF7A6"))
                        st.plotly_chart(fig8)
                    else:
                        st.write("No Wait Time for Resources")

            #Triage patients bar chart
            with st.expander("Triage Categories", expanded = True):

                triage_categories = ["Immediate", "Very Urgent", "Urgent", "Standard", "Non-Urgent"]
                triage_values = [a_and_e.num_patient_immediate, a_and_e.num_patient_very_urgent, a_and_e.num_patient_urgent, a_and_e.num_patient_standard, a_and_e.num_patient_non_urgent]
                fig9 = px.bar(x = triage_categories,  y = triage_values, title = " Number of Patients in Triage Caregories", labels = {"x": " Triage Categories", "y": "Number of Patients"})
                fig9.update_traces(marker=dict(color=["#FF6666", "#FFCC66", "#FFFF66", "#66FF66", "#66CCFF"]))
                st.plotly_chart(fig9)
            
            

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
                    
                    fig10  = px.bar( x = stage_names, y = average_time_for_stages, title = "Average Time for Stages in different stages (patient flow)", labels = {"x": "Stages", "y": "Average Time (minutes)"})
                    st.plotly_chart(fig10)


                
                with col2:


                    #Number of patients in different stages of the process
                    stage_names = ["Discharged", "Requires Tests", "Requires Medication", "Requires Bed"]
                    stage_count = [a_and_e.num_patient_discharged, a_and_e.num_patient_requires_tests, a_and_e.num_patient_requires_medication, a_and_e.num_patient_requires_bed]
                    fig11 = px.bar(x = stage_names, y =stage_count, title = "Number of Patients in Different Stages of the Process", labels = {"x": "Stages", "y": "Number of Patients"})
                    st.plotly_chart(fig11)
                    
                    
        

            with st.expander("Resource Utilisation", expanded = True):
                clerk_utilization = a_and_e.caculate_resource_utilisation(
                a_and_e.track_clerk_utilisation, num_clerks, simulation_run_time)

                nurse_utilization = a_and_e.caculate_resource_utilisation(
                    a_and_e.track_nurse_utilisation, num_nurses, simulation_run_time)

                bed_utilization = a_and_e.caculate_resource_utilisation(
                    a_and_e.track_bed_utilisation, num_beds, simulation_run_time)

                doctor_utilization = a_and_e.caculate_resource_utilisation(
                    a_and_e.track_doctor_utilisation, num_doctors, simulation_run_time)
                    
                    
                col1, col2 = st.columns(2)


                with col1:
                    st.metric(label="Clerk Utilisation", value=f"{clerk_utilization:.2f}%")
                    st.metric(label="Nurse Utilisation", value=f"{nurse_utilization:.2f}%")

                with col2:
                    st.metric(label="Bed Utilisation", value=f"{bed_utilization:.2f}%")
                    st.metric(label="Doctor Utilisation", value=f"{doctor_utilization:.2f}%")


                    # Extracts data for the resources each
                times_clerk, queue_clerk, usage_clerk = zip(*a_and_e.track_clerk_utilisation)
                times_nurse, queue_nurse, usage_nurse = zip(*a_and_e.track_nurse_utilisation)
                times_bed, queue_bed, usage_bed = zip(*a_and_e.track_bed_utilisation)
                times_doctor, queue_doctor, usage_doctor = zip(*a_and_e.track_doctor_utilisation)

                with col1:
                    fig12 = go.Figure()
                    fig12.add_trace(go.Scatter(x=times_clerk, y=usage_clerk, mode="lines", name="Clerk Usage"))
                    fig12.add_trace(go.Scatter(x=times_clerk, y=queue_clerk, mode="lines", name="Clerk Queue", line=dict(color="red")))
                    fig12.update_layout(title="Clerk Resource Utilisation Over Time", xaxis_title="Simulation Time (minutes)", yaxis_title="Number of Clerks")
                    st.plotly_chart(fig12)

                with col2:
                    fig13 = go.Figure()
                    fig13.add_trace(go.Scatter(x=times_nurse, y=usage_nurse, mode="lines", name="Nurse Usage"))
                    fig13.add_trace(go.Scatter(x=times_nurse, y=queue_nurse, mode="lines", name="Nurse Queue", line=dict(color="red")))
                    fig13.update_layout(title="Nurse Resource Utilisation Over Time", xaxis_title="Simulation Time (minutes)", yaxis_title="Number of Nurses")
                    st.plotly_chart(fig13)

                with col1:
                    fig14 = go.Figure()
                    fig14.add_trace(go.Scatter(x=times_doctor, y=usage_doctor, mode="lines", name="Doctor Usage"))
                    fig14.add_trace(go.Scatter(x=times_doctor, y=queue_doctor, mode="lines", name="Doctor Queue", line=dict(color="red")))
                    fig14.update_layout(title="Doctor Resource Utilisation Over Time", xaxis_title="Simulation Time (minutes)", yaxis_title="Number of Doctors")
                    st.plotly_chart(fig14)

                with col2:
                    fig15 = go.Figure()
                    fig15.add_trace(go.Scatter(x=times_bed, y=usage_bed, mode="lines", name="Bed Usage"))
                    fig15.add_trace(go.Scatter(x=times_bed, y=queue_bed, mode="lines", name="Bed Queue", line=dict(color="red")))
                    fig15.update_layout(title="Bed Resource Utilisation Over Time", xaxis_title="Simulation Time (minutes)", yaxis_title="Number of Beds")
                    st.plotly_chart(fig15)
