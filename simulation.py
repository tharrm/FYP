import simpy as sp
import random
import numpy as np
import matplotlib.pyplot as plt

wait_time = [] #List all the wait times for patients
queue_length = [] #List all the queue lengths for patients



#Creates the simulation environment 
class AnE:
    def __init__(self, env, num_doctors, num_nurses, num_beds, num_clerk):
        self.env = env
        self.doctor = sp.Resource(env, num_doctors)
        self.nurse = sp.Resource(env, num_nurses)
        self.bed = sp.Resource(env, num_beds)
        self.clerk = sp.Resource(env, num_clerk) 

    

    
    #patient is the process
    def patient_generator(self, mean_interarrival_time, wait_time, queue_length):
        patient_id=0
        while True:
                patient_id+=1
                interarrival_time= np.random.exponential(mean_interarrival_time)
                yield self.env.timeout(interarrival_time) 
                print(f"Patient arrived at {self.env.now}")
                self.env.process(self.patient_flow(patient_id,wait_time,queue_length))
                
    
    def patient_flow(self, patient_id,wait_times,queue_length):
        yield self.env.process(self.patient_request_admission())
        yield self.env.process(self.patient_request_nurse_for_risk_assesment( patient_id,wait_times,queue_length))
        yield self.env.process(self.patient_request_doctor_for_doctor_consultation(patient_id))
        print(f"Patient {patient_id} has left the A&E at {self.env.now}")

    def patient_request_admission(self):
         #Request general data in the reception 
         req = self.clerk.request()
         yield req 
         print(f"Clerk assigned to patient at {self.env.now}")

         #Stimulate the admission process
         yield env.timeout(random.randint(1,5))
         print(f"Admission completed at {self.env.now}")
         #aRelease the clerk
         self.clerk.release(req)
         print(f"Clerk released at {self.env.now}")
    def triage_manchester(self):
        patient_urgency= {
                        "Red (Immediate)": 5, # 5% chance of being immediate
                        "Orange (Very Urgent)": 10, # 10% chance of being very urgent
                        "Yellow (Urgent)": 35, #35% chance of being urgent
                        "Green (Standard)": 30, #30% chance of being standard
                        "Blue (Non-Urgent)": 20, #20% chance of being non-urgent
                    }
        triage_calculator= random.choices(list(patient_urgency.keys()), weights=patient_urgency.values())[0]#Randomly selects a traige based on the weights and then selects the first element from the list
        return triage_calculator




    def patient_request_nurse_for_risk_assesment (self,patient_id,wait_times,queue_length):
            queue_length.append(len(self.nurse.queue)) # This tracks the length of the queue before the nurse is accomodated
            #Request a nurse for risk assessment
            req= self.nurse.request()
            yield req # Wait for the nurse to be avaailale
            print(f"Nurse assigned to patient {patient_id} at {self.env.now}")

            #Simulate the risk assesment process
            yield self.env.timeout(random.randint(1,5))
            triage_category= self.triage_manchester()
            print(f"Risk assesment for patient {patient_id} completed at {self.env.now}")
            print(f"Patient {patient_id} triaged as {triage_category}")

            #Release the nurse
            self.nurse.release(req)
            print(f"Nurse released at {self.env.now}")
            wait_times.append(self.env.now)
            queue_length.append(len(wait_times))

    def patient_request_doctor_for_doctor_consultation(self,patient_id):
         #Request a doctor for consulation
         req = self.doctor.request()
         yield req # Wait for the doctor to be avavaible 
         print(f"Doctor assigned to patient {patient_id} at {self.env.now}")
        
         #Stimulate the doctor consultation process 
         yield self.env.timeout(random.randint(1,5))
         print(f"Doctor Consultation completed at {self.env.now}")
         decision =random.uniform(0,1)
         if decision <0.5:
                print(f"Patient {patient_id} is discharged at {self.env.now}")
         elif decision<0.9:
              yield self.env.process(self.patient_request_tests(patient_id))
         else:
              yield self.env.process(self.patient_request_medication(patient_id))
         #Release the doctor
         self.doctor.release(req)
         print(f"Doctor released at {self.env.now}")
     
    def patient_rest_request_tests(self,patient_id):
     req = self.nurse.request()
     yield req
     print(f"Nurse assigned to patient {patient_id} at {env.now}")
     yield env.timeout(random.randint(1,5))
     print(f" {patient_id} 's tests completed at {env.now} ")
     self.nurse.release(req)
     print(f"Nurse released at {env.now}")
     yield self.env.process(self.patient_request_doctor_for_doctor_consultation(patient_id))


    def patient_request_medication(self,patient_id):
     print("Hello")






#Creates the simulation environmnment (A&E)
env = sp.Environment()
# Create the A&E department with resources
a_and_e = AnE(env, num_doctors=9, num_nurses=10, num_beds=5, num_clerk=1)
mean_interarrival_time=3
env.process(a_and_e.patient_generator(mean_interarrival_time,wait_time,queue_length))
env.run(until=200)

#Trying to do some visualisation of the data captured
#Plot the queue length
plt.plot(queue_length) 
plt.xlabel("Time")
plt.ylabel("Queue Length")
plt.show()

   