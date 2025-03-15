import simpy as sp
import random
import numpy as np
import matplotlib.pyplot as plt

patient_total_wait_time = [] #List all the wait times for patients
patient_spent_time=[]# List the time the patient spent in the A&E


#Creates the simulation environment 
class AnE:
    def __init__(self, env, num_doctors, num_nurses, num_beds, num_clerk):
        self.env = env
        self.doctor = sp.PriorityResource(env, num_doctors)
        self.nurse = sp.PriorityResource(env, num_nurses)
        self.bed = sp.Resource(env, num_beds)
        self.clerk = sp.Resource(env, num_clerk) 
        self.patient_id=0

    

    
    #patient is the process
    def patient_generator(self, mean_interarrival_time, patient_spent_time, patient_total_wait_time):
        
        while True:
                self.patient_id+=1
                interarrival_time= np.random.exponential(mean_interarrival_time)
                yield self.env.timeout(interarrival_time) 
                print(f"Patient arrived at {self.env.now}")
                self.env.process(self.patient_flow(patient_spent_time, patient_total_wait_time))
                
     #The stages of what the patient goes through
    def patient_flow(self,patient_spent_time,patient_total_wait_time):
        arrival_time=self.env.now #Records when the patient arrives
        yield self.env.process(self.patient_request_admission(patient_total_wait_time))
        priority=yield self.env.process(self.patient_request_nurse_for_risk_assesment(patient_total_wait_time))
        yield self.env.process(self.patient_request_doctor_for_doctor_consultation(priority,patient_total_wait_time))
        
        total_time_patient_spent = self.env.now - arrival_time
        patient_spent_time.append(total_time_patient_spent)

        print(f"Patient {self.patient_id} has left the A&E at {self.env.now}")
    
    def patient_request_admission(self,patient_total_wait_time):
         arrival_time = self.env.now
         #Request general data in the reception 
         req = self.clerk.request()
         yield req 
         wait_time = self.env.now - arrival_time
         patient_total_wait_time.append(wait_time)
         print(f"Clerk assigned to patient at {self.env.now}")

         #Stimulate the admission process
         yield self.env.timeout(random.randint(1,5))
         print(f"Admission completed at {self.env.now}")
         #aRelease the clerk
         self.clerk.release(req)
         print(f"Clerk released at {self.env.now}")
    def triage_manchester(self):
        patient_urgency= {
                        "Red (Immediate)": (5,0), # 5% chance of being immediate with 0 being the highest prirority
                        "Orange (Very Urgent)": (10,1), # 10% chance of being very urgent
                        "Yellow (Urgent)": (35,2), #35% chance of being urgent
                        "Green (Standard)": (30,3), #30% chance of being standard
                        "Blue (Non-Urgent)": (20,4) #20% chance of being non-urgent
                    }
        triage_calculator= random.choices(list(patient_urgency.keys()), weights= [value[0] for value in patient_urgency.values()])[0] #Randomly selects a traige based on the weights and then selects the first element from the list
        priority = patient_urgency[triage_calculator][1] #Selects the priority of the selected triage
        return triage_calculator, priority 



    
    def patient_request_nurse_for_risk_assesment (self,patient_total_wait_time):
            arrival_time= self.env.now
            #trying to make it  based on patient piriority 
            #Request a nurse for risk assessment
            req= self.nurse.request()
            yield req # Wait for the nurse to be availale
            wait_time = self.env.now - arrival_time
            patient_total_wait_time.append(wait_time)
            (wait_time)
            print(f"Nurse assigned to patient {self.patient_id} at {self.env.now}")
            triage_category, priority = self.triage_manchester()
            print(f"Patient {self.patient_id} triaged as {triage_category} priority")


            #Simulate the risk assesment process time
            yield self.env.timeout(random.randint(1,5))
            #Release the nurse
            self.nurse.release(req)
            print(f"Nurse released at {self.env.now}")
            return priority


    def patient_request_doctor_for_doctor_consultation(self,priority,patient_total_wait_time):
         arrival_time = self.env.now
         #Request a doctor for consulation
         req = self.doctor.request(priority= priority)
         yield req # Wait for the doctor to be avavaible 
         wait_time = self.env.now - arrival_time
         patient_total_wait_time.append(wait_time)
         print(f"Doctor assigned to patient {self.patient_id} at {self.env.now}")
        
         #Stimulate the doctor consultation process 
         yield self.env.timeout(random.randint(1,5))
         print(f"Doctor Consultation completed at {self.env.now}")
         decision =random.uniform(0,1)
         if decision <0.5:
                print(f"Patient {self.patient_id} is discharged at {self.env.now}")
         elif decision<0.9:
              yield self.env.process(self.patient_request_tests(priority,patient_total_wait_time))
         else:
              yield self.env.process(self.patient_request_medication(priority,patient_total_wait_time))
         #Release the doctor
         self.doctor.release(req)
         print(f"Doctor released at {self.env.now}")
     
    def patient_request_tests(self,priority, patient_total_wait_time):
     arrival_time = self.env.now
     req = self.nurse.request()
     yield req
     wait_time = self.env.now - arrival_time
     patient_total_wait_time.append(wait_time)
     print(f"Nurse assigned to patient {self.patient_id} at {self.env.now}")
     yield self.env.timeout(random.randint(1,5))
     print(f" {self.patient_id} 's tests completed at {self.env.now} ")
     self.nurse.release(req)
     print(f"Nurse released at {self.env.now}")
     yield self.env.process(self.patient_request_doctor_follow_up(priority,patient_total_wait_time))

     

    def patient_request_medication(self,priority,patient_total_wait_time):
        arrival_time = self.env.now
        req = self.nurse.request(priority= priority )
        yield req
        wait_time = self.env.now - arrival_time
        patient_total_wait_time.append(wait_time)
        print(f"Nurse assigned to patient {self.patient_id} at {self.env.now}")
        yield self.env.timeout(random.randint(1,5))
        print(f" {self.patient_id} 's medication completed at {self.env.now} ")
        self.nurse.release(req)
        print(f"Nurse released at {self.env.now}")
        yield self.env.process(self.patient_request_doctor_follow_up(priority,patient_total_wait_time))


    def patient_request_doctor_follow_up(self,priority,patient_total_wait_time):
        arrival_time = self.env.now
        req= self.doctor.request(priority= priority)
        yield req
        wait_time = self.env.now - arrival_time
        patient_total_wait_time.append(wait_time)
        print(f"Doctor assigned to patient {self.patient_id} at {self.env.now} for a follow up")
        yield self.env.timeout(random.randint(1,5))
        print(f"Doctor follow up completed at {self.env.now}")

        print(f"Patient {self.patient_id} has left the A&E at {self.env.now}") 
        self.doctor.release(req)
        print(f"Doctor released at {self.env.now}")

        




#Creates the simulation environmnment (A&E)
env = sp.Environment()
# Create the A&E department with resources
a_and_e = AnE(env, num_doctors=9, num_nurses=20, num_beds=5, num_clerk=1)
mean_interarrival_time=3
env.process(a_and_e.patient_generator(mean_interarrival_time, patient_spent_time,patient_total_wait_time))
until= 200
while env.peek()<until: # ensures there are no more events left to process
     env.step()

#This calculates the average waiting time for patients who had to wait
if len(patient_total_wait_time) > 0:
    average_waited_time = sum(patient_total_wait_time) / len(patient_total_wait_time)
    # print(f"The average wait time is {average_waited_time} for the pateints who waited") Testing
else:
    # print("No waiting times recorded") Testing
     average_waited_time = 0

if a_and_e.patient_id>0:
     overall_average_time = sum(patient_total_wait_time) /  a_and_e.patient_id
     print(f"The overall average time is {overall_average_time} for all the patients") #Testing
else:
        ("No patient count recorded")
        overall_average_time = 0
