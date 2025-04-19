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
                 admission_duration, risk_assessment_duration, doctor_consultation_duration, test_duration, medication_duration, follow_up_duration, length_of_stay, setup_time,
                 probability_discharge, probability_tests, probability_medication, percentage_hospitilisation_surgery,
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
        self.setup_time = setup_time

        # Probablity of discharge, tests and medications
        self.percentage_discharge = probability_discharge
        self.percentage_tests = probability_tests
        self.percentage_medication = probability_medication
        self.percentage_hospitilisation_surgery = percentage_hospitilisation_surgery 
       
       
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

        self.patient_log = []

        



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

                self.patient_log.append(f"Patient {patient_ID} arrived at {self.sim_format_time(self.env.now)}" + '\n')
                    
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
             self.patient_log.append(f"Patient {patient_ID} is immediate. Assigning a bed at {self.sim_format_time(self.env.now)}" + '\n')
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
         self.patient_log.append(f"Patient {patient_ID} is waiting for a clerk at {self.sim_format_time(self.env.now)}"+ '\n')
         
         #Request general data in the reception 
         req = self.clerk.request()
         yield req 
         
         wait_time = self.env.now - arrival_time
         if wait_time > 0:
            self.track_waiting_time_for_clerk.append(wait_time)

         self.patient_total_wait_time.append(wait_time)
         if wait_time > 0:
            self.patient_who_waited.append(wait_time)
      
         self.patient_log.append(f"Patient {patient_ID} was assigned a Clerk at {self.sim_format_time(self.env.now)}"+ '\n')

         #Stimulate the admission process
         #yield self.env.timeout(random.randint(1,5))
         yield self.env.timeout(self.admission_duration)
         finish_time = self.env.now
         duration = finish_time - arrival_time
         self.track_time_admission.append(duration)
         self.patient_log.append(f"Patient {patient_ID}'s admission completed at {self.sim_format_time(self.env.now)}"+ '\n')
         
         #aRelease the clerk
         self.clerk.release(req)
         self.patient_log.append(f"Patient {patient_ID}'s clerk released at {self.sim_format_time(self.env.now)}"+ '\n')
    
    
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


            
            triage_category, priority = self.triage_manchester()
            self.patient_log.append(f"Patient {patient_ID} triaged as {triage_category} priority"+ '\n')


            #Simulate the risk assesment process time
            yield self.env.timeout(self.risk_assesment_duration)
            finish_time = self.env.now
            duration = finish_time - arrival_time
            self.track_time_risk_assessment.append(duration)
            #Release the nurse
            self.nurse.release(req)
            self.patient_log.append(f"Patient {patient_ID}'s nurse  was released at {self.sim_format_time(self.env.now)}"+ '\n')
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
        
        self.patient_log.append(f"Patient {patient_ID} was assigned a Doctor assigned at {self.sim_format_time(self.env.now)}"+ '\n')
        yield self.env.timeout(self.doctor_consultation_duration)
        finish_time = self.env.now
        duration = finish_time - arrival_time
        self.track_time_doctor_consultation.append(duration)
        self.patient_log.append(f"Patient {patient_ID}'s treatment completed at {self.sim_format_time(self.env.now)}"+ '\n')
        self.doctor.release(req)


    def update_bed_occupancy(self):
        self.track_bed_usage.append((self.env.now,self.occupied_beds))




    def patient_request_bed(self,patient_ID,priority):
        arrival_time= self.env.now 
        self.num_patient_requires_bed += 1
               
        req= self.bed.request()  #Request a bed for the patient
        yield req # Wait for the bed to be avaiable

        patient_bed_wait_time = self.env.now  - arrival_time
        self.patient_total_wait_time.append(patient_bed_wait_time)

        if patient_bed_wait_time > 0:
            self.patient_who_waited.append(patient_bed_wait_time)
            self.track_waiting_time_for_bed.append(patient_bed_wait_time)
        
        self.occupied_beds += 1 
        self.update_bed_occupancy()

        self.patient_log.append(f"Patient {patient_ID} has been assigned a bed at {self.sim_format_time(self.env.now)}"+ '\n')
                         
        

        req_nurse = self.nurse.request(priority = priority)
        yield req_nurse # Wait for the nurse to be available 

        wait_nurse_time = self.env.now - arrival_time
        self.patient_total_wait_time.append(wait_nurse_time)


        if wait_nurse_time > 0:
                self.patient_who_waited.append(wait_nurse_time)
                self.track_waiting_time_for_nurse.append(wait_nurse_time)
        
        
        self.patient_log.append(f"Patient {patient_ID} was assigned a Nurse at {self.sim_format_time(self.env.now)}"+ '\n')

        yield self.env.timeout(self.setup_time) # Stimulate the bed set up

        self.nurse.release(req_nurse)

        
        self.patient_log.append(f"Patient {patient_ID} bed set up completed at {self.sim_format_time(self.env.now)} "+ '\n')       
        
        yield self.env.process(self.patient_gets_doctor(patient_ID))              

            
          
        #Stimulate the length of stay (LOS) in the bed
        bed_start_time = self.env.now
        yield self.env.timeout(self.length_of_stay)
        self.update_last_patient_time()
        
        
        self.patient_log.append(f"Patient {patient_ID} has left the bed at {self.sim_format_time(self.env.now)}"+ '\n')

        #Bed gets released and gets updated
        self.occupied_beds -= 1
        self.bed.release(req)
        self.update_bed_occupancy()

        # Calculate the length of stay (LOS) for the patient
        los = self.env.now - bed_start_time
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
          
            
            self.patient_log.append(f"Patient {patient_ID} was assigned to a Doctor at {self.sim_format_time(self.env.now)}" + '\n')
        
            #Stimulate the doctor consultation process 
            #yield self.env.timeout(random.randint(1,5))
            yield self.env.timeout(self.doctor_consultation_duration)
            
            self.patient_log.append(f"Patient {patient_ID}'s Doctor Consultation was completed at {self.sim_format_time(self.env.now)}"+ '\n')
            finish_time = self.env.now
            duration = finish_time - arrival_time
            self.track_time_doctor_consultation.append(duration)
            
            total = self.percentage_discharge + self.percentage_tests + self.percentage_medication + self.percentage_hospitilisation_surgery
            
            if total ==0:
                self.percentage_discharge = 100/4
                self.percentage_tests = 100/4
                self.percentage_medication = 100/4
                self.percentage_hospitilisation_surgery = 100/4

            
            if total != 100:
                self.percentage_discharge = (self.percentage_discharge / total) * 100 
                self.percentage_tests = (self.percentage_tests / total) * 100
                self.percentage_medication = (self.percentage_medication / total) * 100
                self.percentage_hospitilisation_surgery = (self.percentage_hospitilisation_surgery / total) * 100
            
            
            #decision =random.uniform(0,1)
            decision = random.choices(["Discharge", "Tests", "Medication", "Hospitilisation"], weights = [self.percentage_discharge, self.percentage_tests, self.percentage_medication, self.percentage_hospitilisation_surgery])[0]
            
            if decision == "Discharge":
                self.track_time_for_discharge.append(duration)
                self.update_last_patient_time()
                self.patient_log.append(f"Patient {patient_ID} is discharged at {self.sim_format_time(self.env.now)}"+ '\n')
                self.num_patient_discharged += 1
                

                 #Release the doctor
                self.doctor.release(req)
                self.patient_log.append(f"Patient {patient_ID}'s Doctor released at {self.sim_format_time(self.env.now)}"+ '\n')
            elif decision == "Tests":
               self.num_patient_requires_tests += 1
               
               self.patient_log.append(f"Patient {patient_ID} needs to do tests"+ '\n')
               #Release the doctor
               self.doctor.release(req)
               
               self.patient_log.append(f"Patient {patient_ID}'s Doctor released at {self.sim_format_time(self.env.now)}"+ '\n')
               yield self.env.process(self.patient_request_tests(patient_ID,priority))
              
            elif decision == "Medication":
              self.num_patient_requires_medication += 1
              self.patient_log.append(f"Patient {patient_ID} needs to take medication"+ '\n')
              #Release the doctor
              self.doctor.release(req)
              self.patient_log.append(f"Patient {patient_ID}'s Doctor released at {self.sim_format_time(self.env.now)}"+ '\n')
              yield self.env.process(self.patient_request_medication(patient_ID,priority))
            
            elif decision == "Hospitilisation":
                self.num_patient_requires_bed += 1
                self.patient_log.append(f"Patient {patient_ID} needs to be admitted to for hospitilisation or surgery at {self.sim_format_time(self.env.now)}"+ '\n')
                
                yield self.env.process(self.patient_request_bed(patient_ID, priority))
         
     
    def patient_request_tests(self,patient_ID, priority):
     arrival_time = self.env.now
     req = self.nurse.request(priority= priority )
     yield req

     wait_time = self.env.now - arrival_time
     self.patient_total_wait_time.append(wait_time)
     if wait_time > 0:
            self.patient_who_waited.append(wait_time)
            self.track_waiting_time_for_nurse.append(wait_time)

     self.patient_log.append(f"Patient {patient_ID} was assigned to a Nurse at {self.sim_format_time(self.env.now)}"+ '\n')
     #yield self.env.timeout(random.randint(1,5))
     yield self.env.timeout(self.test_duration)
     
     finish_time = self.env.now
     duration = finish_time - arrival_time
     self.track_time_tests.append(duration)
    
     self.patient_log.append(f"Patient {patient_ID} 's tests completed at {self.sim_format_time(self.env.now)}"+ '\n')
     self.nurse.release(req)
     self.patient_log.append(f"Patient {patient_ID}'s Nurse released at {self.sim_format_time(self.env.now)}"+ '\n')
     yield self.env.process(self.patient_request_doctor_follow_up(patient_ID, priority))

     

    def patient_request_medication(self,patient_ID,priority):
        arrival_time = self.env.now
        req = self.nurse.request(priority= priority )
        yield req
        self.patient_log.append(f"Patient {patient_ID} with priority {priority} was assigned to  a Nurse at {self.sim_format_time(self.env.now)}"+ '\n')
        wait_time = self.env.now - arrival_time
        self.patient_total_wait_time.append(wait_time)
        if wait_time > 0:
            self.patient_who_waited.append(wait_time)
            self.track_waiting_time_for_nurse.append(wait_time)
        self.patient_log.append(f"Patient {patient_ID} was assigned to a Nurse at {self.sim_format_time(self.env.now)}"+ '\n')
        #yield self.env.timeout(random.randint(1,5))
        yield self.env.timeout(self.medication_duration)
        self.patient_log.append(f"Patient {patient_ID} finished medication at {self.sim_format_time(self.env.now)}" + '\n')
        
        finish_time = self.env.now
        duration = finish_time - arrival_time
        #print(f"Duration " + duration)
        self.track_time_medication.append(duration)
        self.patient_log.append(f"Patient {patient_ID}'s medication completed at {self.sim_format_time(self.env.now)}"+ '\n')
        self.nurse.release(req)
        self.patient_log.append(f"Patient {patient_ID}'s Nurse released at {self.sim_format_time(self.env.now)}"+ '\n')
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
        self.patient_log.append(f"Patient {patient_ID} was assigned to a Doctor for a follow up at {self.sim_format_time(self.env.now)}"+ '\n')
        #yield self.env.timeout(random.randint(1,5))
        yield self.env.timeout(self.follow_up_duration)
        finish_time = self.env.now
        duration = finish_time - arrival_time
        self.track_time_for_follow_up.append(duration)

        self.patient_log.append(f"Patient {patient_ID}'s Doctor follow up completed at {self.sim_format_time(self.env.now)}"+ '\n')
    
        self.update_last_patient_time()
        
        self.patient_log.append(f"Patient {patient_ID} has left the A&E at {self.sim_format_time(self.env.now)}"+ '\n') 
        
        self.doctor.release(req)

        self.patient_log.append(f"Patient {patient_ID}'s Doctor released at {self.sim_format_time(self.env.now)}"+ '\n')
    
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

#st.title("A&E Simulation 🏥")
st.markdown("<p style =  'font-size:55px; font-weight:bold; text-align: center;'>A&E Simulation🏥</p>", unsafe_allow_html=True)
#st.write("Testing")
with st.expander(label = "About", expanded = False):
        st.subheader("About the A&E Simulation", anchor = False)
        st.write("This web application presents you with a configurable Accident and Emergency (A&E) simulation. It generates results to help you and other users identify bottlenecks and assist in making well-informed decisions on ways to enhance overall efficiency. Patient flow refers to the movement process of patients through the A&E department, from when they arrive to when they are discharged. Bottlenecks, such as queues or waiting periods, may be identified with this system, and the overall efficiency of the system can be improved")
        st.write("This simulation is a type of Discrete Event Simulation (DES) that allows us to make observations at certain points of time, where changes take place in the system - such as when a patient arrives; when they are seen by a doctor; or when they get discharged. This enables us to capture the dynamic nature of the system, analyse how various factors impact patient flow, and identify solutions to enhance it.")
        st.write("The A&E Simulation is designed to be customisable through parametisation. This application is flexible as it enables you to experiment with different configurations, creating scenarios. From these scenarios, users can observe the impact on waiting times, resource usage, and other factors to help identify bottlenecks. To configure the parameters, it is located at the left side panel under **⚙️ Simulation Configuration**.")
        st.subheader("Simulation Configuration Explained", anchor = False)
   
        st.markdown("<p style='font-size:15px; font-weight:bold;'> 1. Resource Allocation</p>", unsafe_allow_html = True)
        st.write("This section allows you to configure the number of healthcare professionals and beds available. These are known as “resources” in the simulation, which are the entities that are used to process patients. In other words, they are resources since they are limited and shared among all patients. Proper resource management is crucial for patient flow and lowering wait times. If a resource is busy, Patients will have to wait and a queue will be formed.")
        st.write(" - **👩‍💼 Number of Clerks**: Clerks handle patient registration and administrative tasks" )
        st.write(" - **👩‍⚕️ Number of Nurses**: Nurses conduct initial assesments and triage patients")
        st.write(" - **👨‍⚕️ Number of Doctors**: Doctors provide consultations and treatments.")
        st.write(" - **🛏️ Number of Beds**: Beds are used to accomodate patients who requires further treatment or observation ")
    
        st.markdown("<p style='font-size:15px; font-weight:bold;'> 2. Triage Allocation</p>", unsafe_allow_html = True)
        st.write("Patients are categorised according to the urgency and severity of their condition, known as “triage”. The system applied in this simulation is the Manchester triage, which is widely used to classify patients into five colour-coded categories, resulting in an order in which patients receive treatment first. The triage model should sum up to 100%.")
        st.write(" - **🔴 Immediate Patients (%)**: Life-threatning conditions")
        st.write(" - **🟠 Very Urgent Patients(%)**: Severe but non-life threatening")
        st.write(" - **🟡 Urgent Patients (%)**: Moderate conditions requring prompt care ")
        st.write(" - **🟢 Standard Patients (%)**: Less critical but need attention")
        st.write(" - **🔵 Non-Urgent Patients (%)**: Low-risk cases")

        st.markdown("<p style='font-size:15px; font-weight:bold;'> 3. Patient Flow</p>", unsafe_allow_html = True)
        st.write("- **🔁Admission Duration**: Time taken by the clerk to register a patient")
        st.write("- **⚠️ Risk Assesment Duration**: Time taken by nurses to assess and triage a patient")
        st.write("- **🩺 Doctor Consultation Duration**: Time taken by a doctor to peform a consultation to a patient")
        st.write("- **🧪 Test Duration**: Time required for lab tests")
        st.write("- **💊 Medication Duration**: Time required for the medication process")
        st.write("- **👩‍💼 Doctor Follow Up Duration**: A follow up consultation conducted by a doctor after a treatment ")
        st.write("- **🏥 Length of Stay**: Time spent in bed")
        st.write("The likelihood of a patient being discharged, requiring tests or medication. The percentages need to add up to 100%.")
        st.write("- **📤 Percentage of Discharge:**: Patients who leave A&E without anymore check-ups")
        st.write("- **🧬 Percentage of Tests**: Patients requiring diagnostic tests")
        st.write("- **💉 Percentage of Medication**: Patients needing medication for treatment")
        st.write("- **🏥 Percentage of Hospitilisation/Surgery**: Patients not regarded as immeidate but require surgery or hospitlisation")

        st.markdown("<p style='font-size:15px; font-weight:bold;'> 4. Patient Generator</p>", unsafe_allow_html = True)
        st.write("This section lets you control how frequently new patients arrive at the A&E department. The mean arrival time is the average time between patient arrivals. A lower value would mean more frequent arrivals, while a higher value means less frequent. This was done exponentially, to make it as random as possible." )
        st.write( " - **🚶‍♀️‍➡️Mean Arrival Time**:  How much patient arrives")
    
    
    
        st.markdown("<p style='font-size:15px; font-weight:bold;'> 5. Time Configuration</p>", unsafe_allow_html = True)
        st.write("- **🕛Simulation Run Time in Minutes**: The total simulation duration in minutes. But note that the simulation time might exceed to ensure all patients have been processed")
        st.write("- **⏳Start Time**: The time of the day the simulation begins")

        st.markdown("<p style='font-size:15px; font-weight:bold;'> Once all are entered press the run simulation button to start the simulation</p>", unsafe_allow_html = True)
     
with st.sidebar:
    st.markdown("⚙️ <span style = 'font-size: 20px;'>Simulation Configuration</span>", unsafe_allow_html=True)

    with st.expander(label="Resources Allocation", expanded=False):
        #st.markdown("<span style = 'font-size: 20px;'> Configure the number of resources in the A&E department </span>", unsafe_allow_html=True)
        
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 👩‍💼Number of Clerks:</p>", unsafe_allow_html= True)
        num_clerks = st.slider("👩‍💼Number of Clerks", 1, 10, 3)
        #st.markdown("<p style='font-size:20px; font-weight:bold;'>👩‍⚕️Number of Nurses:</p>", unsafe_allow_html= True)
        num_nurses = st.slider("👩‍⚕️Number of Nurses", 1, 20, 10)
        #st.markdown("<p style='font-size:20px; font-weight:bold;'>👨‍⚕️Number of Doctors:</p>", unsafe_allow_html= True)
        num_doctors = st.slider("👨‍⚕️Number of Doctors ", 1, 20, 10)
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🛏️Number of Beds:</p>", unsafe_allow_html= True)
        num_beds = st.slider("🛏️Number of Beds ", 1, 20, 5)
    
    with st.expander(label = "Triage Allocation", expanded = False):
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🔴 % of Immediate Patients:</p>", unsafe_allow_html= True)
        num_immediate = st.number_input( "🔴 % of Immediate Patients ",0, 100, 1)
        
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🟠 % of Very Urgent Patients:</p>", unsafe_allow_html= True)
        num_very_urgent = st.number_input("🟠 % of Very Urgent Patients:", 0, 100,1)
        
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🟡 % of Urgent Patients:</p>", unsafe_allow_html= True)
        num_urgent = st.number_input( "🟡 % of Urgent Patients", 0, 100, 1)
        
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🟢 % of Standard Patients:</p>", unsafe_allow_html= True)
        num_standard = st.number_input("🟢 % of Standard Patients",0,100,1)
        
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🔵 % of Non-Urgent Patients:</p>", unsafe_allow_html= True)
        num_non_urgent = st.number_input("🔵 % of Non-Urgent Patients",0, 100, 1)

        	
         # Validate that the sum of percentages equals 100
        total_percentages = num_immediate + num_very_urgent + num_urgent + num_standard + num_non_urgent
        if total_percentages != 100:
            st.warning(f"The total percentage of triage categories is {total_percentages}%. Please ensure it equals 100%.")

    with st.expander(label = "Patient Flow", expanded= False):
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🔁Admission Duration:</p>", unsafe_allow_html= True)
        admission_duration = st.slider("🔁Admission Duration", 1, 10, 5)
       
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> ⚠️Risk Assesment Duration:</p>", unsafe_allow_html= True)

        risk_assessment_duration = st.slider("⚠️Risk Assesment Duration ", 1, 10, 5)
        
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🩺Doctor Consultation Duration:</p>", unsafe_allow_html= True)
        doctor_consultation_duration = st.slider("🩺Doctor Consultation Duration ", 1, 10, 5)
        
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🧪Test Duration:</p>", unsafe_allow_html= True)
        test_duration= st.slider("🧪Test Duration ", 1, 20, 5)
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 💊 Medication Duration</p>", unsafe_allow_html= True)
        medication_duration = st.slider("💊 Medication Duration ", 1, 30, 5)
        
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 👩‍💼Doctor Follow Up Duration:</p>", unsafe_allow_html= True)
        follow_up_duration = st.slider("👩‍💼Doctor Follow Up Duration", 1, 20, 5)
        
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🏥Length of Stay:</p>", unsafe_allow_html= True)
        length_of_stay = st.slider("🏥Length of Stay", 1, 30, 5)

        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🛏️Bed Set Up Time:</p>", unsafe_allow_html= True)
        setup_time = st.slider(" 🛏️Bed Set Up Time", 1, 10, 5)

        #st.markdown("<p style='font-size:20px; font-weight:bold;'>📤 Percentage of Discharge:</p>", unsafe_allow_html= True)
        percentage_discharge = st.slider("📤 Percentage of Discharge      ", 0, 100, 1)
       
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🧬 Percentage of Tests:</p>", unsafe_allow_html= True)
        percentage_tests = st.slider(" 🧬 Percentage of Tests          ", 0, 100, 1)
       
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 💉Percentage of Medication:</p>", unsafe_allow_html= True)
        percentage_medication = st.slider(" 💉Percentage of Medication ",0, 100, 1)


        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 💉Percentage of Hospitilisation/Surgery:</p>", unsafe_allow_html= True)
        percentage_hospitilisation_surgery = st.slider("💉Percentage of Hospitilisation/Surgery", 0, 100, 1)
        # Validate that the sum of percentages equals 100 
        total_percentage = percentage_discharge + percentage_tests + percentage_medication + percentage_hospitilisation_surgery
        if total_percentage != 100:
            st.warning(f"The total percentage of Patient Flow categories is {total_percentage}%. Please ensure it equals 100%.")
        
    
    with st.expander(label = " Patient Generator", expanded = False):
       # st.markdown("<p style='font-size:20px; font-weight:bold;'> 🚶‍♀️‍➡️Mean Arrival Time:</p>", unsafe_allow_html= True)
            mean_interarrival_time = st.slider("🚶‍♀️‍➡️Mean Arrival Time ", 1, 10,3 )
        #average_rate_patients_per_interval = st.slider(" 🚶‍♂️‍➡️Average Rate of Patients per Interval", 1, 50, 10)




    with st.expander(label = "Simulation Configuration", expanded = False):
        #st.markdown("<p style='font-size:20px; font-weight:bold;'> 🕛Simulation Run Time in minutes</p>", unsafe_allow_html= True)

        simulation_run_time= st.number_input("🕛Simulation Run Time in minutes", 1, 1440, 100)
        
      #  st.markdown("<p style='font-size:20px; font-weight:bold;'>⏳ Start Time:</p>", unsafe_allow_html= True)
        start_time = st.time_input("⏳ Start Time", datetime(2025, 3, 15, 8, 0).time())


    if "simulation_stopped" not in st.session_state:
        st.session_state.simulation_stop = False
    

    

    run_button_pressed = False # Initial Value      
    if st.button("▶️ Run Simulation"):
       st.cache_data.clear()
       if (total_percentage + total_percentages !=200):
           if total_percentages != 100:
                st.error("Please check the triage percentages. They need to add up to 100%")
           if total_percentage !=100:
               st.error("Please check the patient flow percentages. They need to add up to 100%")

       else:
           run_button_pressed = True
           st.session_state.simulation_stop = False

    

if run_button_pressed and not st.session_state.simulation_stop:

        #This clears the previous simulation run of the patient log data
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
                      admission_duration, risk_assessment_duration, doctor_consultation_duration, test_duration, medication_duration, follow_up_duration, length_of_stay,setup_time,
                      percentage_discharge, percentage_tests, percentage_medication, percentage_hospitilisation_surgery,
                      start_time
                                            
                      )
        env.process(a_and_e.patient_generator(mean_interarrival_time,simulation_run_time))
        env.process(a_and_e.resource_utilisation_tracker())
        
        if  st.button("🛑 Stop Simulation"):
                st.session_state.simulation_stop = True
        
        with st.spinner("Running Simulation"):
           
            
            while env.peek() <= simulation_run_time and not st.session_state.simulation_stop:
                env.step()
                
            while a_and_e.active_patients != set() and not  st.session_state.simulation_stop:
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
                patient_log = "\n".join(a_and_e.patient_log)
                st.session_state.patient_log_data = patient_log 
                st.subheader("Patient Log", anchor = False, divider = True)
               
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

            with st.expander(label = " ℹ️ Visualation Guide Info", expanded = False):
                st.markdown("<p style='font-size:15px; font-weight:bold;'>1. Resource Utilisation (%)</p>", unsafe_allow_html = True)
                st.write("The percentage stats shows the overall resource utilisation efficiency through out the simulation. ")
                st.write("These graphs illustrate the efficency of the resources (clerks, nurses, doctors and beds) utilised throughout the simulation. High utilisation percentages refelct substantial demand, which may result in increase in patient waiting times. Where as low utilisation percentages indicate that the resources are underutilised, which may suggest that theres a surplus of resources.")

                st.markdown("<p style='font-size:15px; font-weight:bold;'>2. Length of Stay for Patients Occupied in Bed</p>", unsafe_allow_html = True)
                st.write("The box plot displays the distribution of patient bed stays. This can help identify outliers and asses the efficiency of patient flow.")

                st.markdown("<p style='font-size:15px; font-weight:bold;'>3. Time Patients Spent in A&E</p>", unsafe_allow_html = True)
                st.write("These graphs visualises how long patients typically stay in A&E. This can potentially highlight bottlenecks in the A&E")

                st.markdown("<p style='font-size:15px; font-weight:bold;'>4. Patient Wait Time</p>", unsafe_allow_html = True)
                st.write("The histogram and box plot show the distribution of patient wait times before receiving care. Longer wait times indicates bottlenecks in the system.")

                st.markdown("<p style='font-size:15px; font-weight:bold;'>5. Resource Wait Times</p>", unsafe_allow_html = True)
                st.write("This bar chart displays the average waiting times for different resources (clerks, nurses, doctors and beds). It indentify which resource is causing the most delays.This then can higlight the need to re-allocate resources to optimise patient flow.")


                st.markdown("<p style='font-size:15px; font-weight:bold;'>6. Triage Categories </p>", unsafe_allow_html = True)
                st.write("The bar chart shows the number of patients in different triage categories.")


                st.markdown("<p style='font-size:15px; font-weight:bold;'>7. Patient Flows</p>", unsafe_allow_html = True)
                st.write("These graphs shows the average time and how long patients spent in each stages of the A&E process.")


                st.markdown("<p style='font-size:15px; font-weight:bold;'>8. Resource Utilisation and Queue Over Time</p>", unsafe_allow_html = True)
                st.write("These graphs shows the resources utilisation and queue over time. The y-axis represents both the number of resources in use and the the number of patients waiting in queue for that resource. The red line shows how many patients are waiting. The blue line indicates how many resources are actively being used over time. If the red line is above the blue line, it highlights that there is a high demand as its exceeding the capacity of the resources. It signals that resources need to be scaled up in order to meet the demand more effectively.")

               

                


            with st.expander("Resources Utilisation (%)", expanded=True):
                st.subheader("Overall Resource Utilisation (%)", anchor = False, divider = "gray")

                #This calculates the resource utilisation for every resource
                clerks_utilisation = a_and_e.caculate_resource_utilisation(a_and_e.track_clerk_utilisation, num_clerks, simulation_run_time)

                nurses_utilisation = a_and_e.caculate_resource_utilisation(a_and_e.track_nurse_utilisation, num_nurses, simulation_run_time)

                beds_utilisation = a_and_e.caculate_resource_utilisation(a_and_e.track_bed_utilisation, num_beds, simulation_run_time)

                doctors_utilisation = a_and_e.caculate_resource_utilisation(a_and_e.track_doctor_utilisation, num_doctors, simulation_run_time)
                    
                    
                col1, col2 = st.columns(2)

                with col1:
                    st.metric(label="Clerk Utilisation", value=f"{clerks_utilisation:.2f}%")
                    st.metric(label="Nurse Utilisation", value=f"{nurses_utilisation:.2f}%")

                with col2:
                    st.metric(label="Bed Utilisation", value=f"{beds_utilisation:.2f}%")
                    st.metric(label="Doctor Utilisation", value=f"{doctors_utilisation:.2f}%")
                
                
                
                st.subheader("Resource Utilisation (%) Over Time", anchor = False, divider = "gray")

                col1, col2 = st.columns(2)

                with col1:

                    if a_and_e.track_bed_utilisation:
                        #print(a_and_e.track_bed_usage) Testing 
                        times, queue_bed,bed_count = zip(*a_and_e.track_bed_utilisation)  # This unpacks into two lists time and bed count 
                        
                
                        bed_utilisation = []
                        for count in bed_count:
                            bed_utilisation.append((count / num_beds) * 100)


                        #This graph is for bed occupancy over time 
                        fig1 = px.line(x=times, y=bed_utilisation, labels={"x": "Simulation Time (minutes)", "y": "Utilisation (%)"}, title = "Bed Utilisation (%) Over Time", line_shape= "linear")
                        fig1.update_traces(line = dict(color = "purple"))
                        st.plotly_chart(fig1)
                    else:
                        st.write("No data as beds were not used")
                with col2:

                    if a_and_e.track_clerk_utilisation:
                        clerk_times, queue_clerk, clerk_count = zip(*a_and_e.track_clerk_utilisation)

                        clerk_utilisation = []
                        for count in clerk_count:
                            clerk_utilisation.append((count / num_clerks) * 100)
                            
                        #Display Graph for clerk utilisation

                        fig17 = px.line(x=clerk_times, y=clerk_utilisation, labels={"x": "Simulation Time (minutes)", "y": "Utilisation (&)"}, title = "Clerk Utilisation (%) Over Time", line_shape = "linear")
                        fig17.update_traces(line = dict(color = "blue"))
                        st.plotly_chart(fig17)
                    else:
                        st.write("No data as clerks were not used")
                
                with col1: 
                    if a_and_e.track_doctor_utilisation:
                        doctor_times, queue_doctor, doctor_count = zip(*a_and_e.track_doctor_utilisation)


                        doctor_utilisation = []
                        for count in doctor_count:
                            doctor_utilisation.append((count / num_doctors) * 100)
                        
                        fig18 = px.line(x=doctor_times, y=doctor_utilisation, labels={"x": "Simulation Time (minutes)", "y": "Utilisation (&)"}, title = "Doctor Utilisation (%) Over Time", line_shape = "linear")
                        fig18.update_traces(line = dict(color = "green"))
                        st.plotly_chart(fig18)
                    else:
                        st.write("No data as doctors were not used")
                
                with col2: 
                    if a_and_e.track_nurse_utilisation:
                        nurse_times, queue_nurse, nurse_count = zip(*a_and_e.track_nurse_utilisation)


                        nurse_utilisation = []
                        for count in nurse_count:
                            nurse_utilisation.append((count / a_and_e.nurse.capacity) * 100)
                        
                        fig19 = px.line(x=nurse_times, y=nurse_utilisation, labels={"x": "Simulation Time (minutes)", "y": "Utilisation (%)"}, title = "Nurse Utilisation (%) Over Time", line_shape = "linear")
                        fig19.update_traces(line = dict(color = "red"))
                        st.plotly_chart(fig19)



                    
                    
                    # #This graph is for bed occupancy over time 
                    # fig21 = px.line(x=times, y=bed_count, labels={"x": "Simulation Time (minutes)", "y": "Occupied Beds"}, title = "Bed Occupancy Over Time", line_shape= "linear")
                    # fig21.update_traces(line = dict(color = "purple"))
                    # st.plotly_chart(fig21)
              

           
            # Length of stay for patients 
            with st.expander("Length of Stay for Patients Occupued in Bed", expanded=True):
                    fig2 = px.box(x=a_and_e.patient_LOS,title="Length of Stay for Patients (Minutes) ", labels={"x": "Length of Stay (minutes)"})                    
                    st.plotly_chart(fig2)
                  
                  
                  

            #This graph is for the time patients spent in the AnE
            with st.expander("Time Patients Spent in A&E", expanded=True):
                col1, col2, col3 = st.columns(3)

                with col1:
                    if len(a_and_e.patient_spent_time) > 0:
                        fig3 = px.box(x=a_and_e.patient_spent_time, title = " Time Patients Spent in A&E (Minutes)", labels = {"x": "Minutes"})
                        st.plotly_chart(fig3)
                    else:
                        st.write("No Patients spent time in A&E")
                    

                with col2:
                    if len(a_and_e.patient_spent_time) > 0:

                        #This graph is for the time patients spent in the AnE
                        fig4= px.violin(y=a_and_e.patient_spent_time, title = "Time Patients Spent in A&E (Minutes)", labels = {"y": "Minutes"})
                        fig4.update_traces(marker=dict(color = "red"))
                        fig4.update_traces(box_visible=True, meanline_visible=True)
                        st.plotly_chart(fig4)
                    else:    
                        st.write("No patient spent time in A&E")

            #Histogram for patient spent time 
                with col3:
                    fig5 = px.histogram(x= a_and_e.patient_spent_time, nbins=int( np.sqrt(len(a_and_e.patient_spent_time))),title = "Distribution of Patient Time Spent in A&E (Minutes)", labels = {"x": "Minutes", "y": "Frequency"})
                    fig5.update_traces(marker=dict(color = "#FFA07A",line=dict(color="black", width=1)))
                    st.plotly_chart(fig5)
              
              

            #This graph is for the average waiting time for patients
            with st.expander("Patient Wait Time", expanded = True):
                col1, col2 = st.columns(2)
                
                with col1:

                    if len(a_and_e.patient_who_waited) > 0:
                       figs = px.histogram(
                           x=a_and_e.patient_spent_time,
                           nbins=int(np.sqrt(len(a_and_e.patient_who_waited))),
                           title="Patient Waiting Time Distribution (Minutes)",
                           labels={"x": "Minutes", "y": "Frequency"}
                       )
                       figs.update_traces(marker=dict(color="#FDB7EA", line=dict(color="black", width=1)))
                       st.plotly_chart(figs)
                    else:
                        st.write("No patient wait times.")

                with col2:
                    if len(a_and_e.patient_who_waited) > 0:

                        fig6 = px.box(x = a_and_e.patient_who_waited, title = "Wait Time for Patients (Minutes)", labels = {"x": "Wait Time (minutes)"})
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
                        fig7 = px.bar(x = resource_names, y = average_resource_wait_time, title = "Average Wait Time by Resource (Minutes)", labels = {"x": "Resources", "y": "Average Wait Time (Minutes)"})
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
                        fig8 = px.bar( x = resource_names, y = resource_wait_time, title = " Cummulative Resource Waiting Time (Minutes)", labels = {"x": "Resources", "y": "Wait Time (Minutes)"}) 
                        fig8.update_traces(marker=dict(color = "#DAF7A6"))
                        st.plotly_chart(fig8)
                    else:
                        st.write("No Wait Time for Resources")

            #Triage patients bar chart
            with st.expander("Triage Categories", expanded = True):

                triage_categories = ["Immediate", "Very Urgent", "Urgent", "Standard", "Non-Urgent"]
                triage_values = [a_and_e.num_patient_immediate, a_and_e.num_patient_very_urgent, a_and_e.num_patient_urgent, a_and_e.num_patient_standard, a_and_e.num_patient_non_urgent]
                fig9 = px.bar(x = triage_categories,  y = triage_values, title = " Triage Category Distribution", labels = {"x": " Triage Categories", "y": "Number of Patients"})
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
                    
                    fig10  = px.bar( x = stage_names, y = average_time_for_stages, title = "Average Time for Patient Journey Through A&E (Minutes per Stage)  ", labels = {"x": "Stages", "y": "Average Time (minutes)"})
                    st.plotly_chart(fig10)


                
                with col2:


                    #Number of patients in different stages of the process
                    stage_names = ["Discharged", "Requires Tests", "Requires Medication", "Requires Bed"]
                    stage_count = [a_and_e.num_patient_discharged, a_and_e.num_patient_requires_tests, a_and_e.num_patient_requires_medication, a_and_e.num_patient_requires_bed]
                    fig11 = px.bar(x = stage_names, y =stage_count, title = "Number of Patients in Different Stages of the A&E", labels = {"x": "Stages", "y": "Number of Patients"})
                    st.plotly_chart(fig11)
                    
                    
        

            with st.expander("Resource Utilisation and Queue Over Time", expanded = True):
                col1, col2 = st.columns(2)


                    # Extracts data for the resources each
                times_clerk, queue_clerk, usage_clerk = zip(*a_and_e.track_clerk_utilisation)
                times_nurse, queue_nurse, usage_nurse = zip(*a_and_e.track_nurse_utilisation)
                times_bed, queue_bed, usage_bed = zip(*a_and_e.track_bed_utilisation)
                times_doctor, queue_doctor, usage_doctor = zip(*a_and_e.track_doctor_utilisation)

                with col1:
                    fig12 = go.Figure()
                    fig12.add_trace(go.Scatter(x=times_clerk, y=usage_clerk, mode="lines", name="Clerk Usage"))
                    fig12.add_trace(go.Scatter(x=times_clerk, y=queue_clerk, mode="lines", name="Clerk Queue", line=dict(color="red")))
                    fig12.update_layout(title="Clerk Resource Utilisation and Queue Over Time ", xaxis_title="Simulation Time (minutes)", yaxis_title="Number of Clerks/Number of Patients in Queue")
                    st.plotly_chart(fig12)

                with col2:
                    fig13 = go.Figure()
                    fig13.add_trace(go.Scatter(x=times_nurse, y=usage_nurse, mode="lines", name="Nurse Usage"))
                    fig13.add_trace(go.Scatter(x=times_nurse, y=queue_nurse, mode="lines", name="Nurse Queue", line=dict(color="red")))
                    fig13.update_layout(title="Nurse Resource Utilisation and Queue Over Time ", xaxis_title="Simulation Time (minutes)", yaxis_title="Number of Nurses/Number of Patients in Queue")
                    st.plotly_chart(fig13)

                with col1:
                    fig14 = go.Figure()
                    fig14.add_trace(go.Scatter(x=times_doctor, y=usage_doctor, mode="lines", name="Doctor Usage"))
                    fig14.add_trace(go.Scatter(x=times_doctor, y=queue_doctor, mode="lines", name="Doctor Queue", line=dict(color="red")))
                    fig14.update_layout(title="Doctor Resource Utilisation and Queue Over Time", xaxis_title="Simulation Time (minutes)", yaxis_title="Number of Doctors/Number of Patients in Queue")
                    st.plotly_chart(fig14)

                with col2:
                    fig15 = go.Figure()
                    fig15.add_trace(go.Scatter(x=times_bed, y=usage_bed, mode="lines", name="Bed Usage"))
                    fig15.add_trace(go.Scatter(x=times_bed, y=queue_bed, mode="lines", name="Bed Queue", line=dict(color="red")))
                    fig15.update_layout(title="Bed Resource Utilisation and Queue Over Time ", xaxis_title="Simulation Time (minutes)", yaxis_title="Number of Beds/Number of Patients in Queue")
                    st.plotly_chart(fig15)
