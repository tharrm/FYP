import simpy as sp
import random
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta


patient_spent_time=[]# List the time the patient spent in the A&E
patient_LOS=[] # Length of stay for the patient if they are admitted to a bed


#Creates the simulation environment 
class AnE:
    def __init__(self, env, num_doctors, num_nurses, num_beds, num_clerk):
        self.env = env
        self.doctor = sp.PriorityResource(env, num_doctors)
        self.nurse = sp.PriorityResource(env, num_nurses)
        self.bed = sp.Resource(env, num_beds)
        self.clerk = sp.Resource(env, num_clerk) 
        self.patient_id=0
        self.start_time = datetime(2025,3,15,8,0)
        self.track_bed_usage = [] # This tracks occupied bed over time 
        self.last_patient_time=0
        self.patient_total_wait_time = [] #List all the wait times for patients
        self.occupied_beds = 0 #Will increment and decrement 



    def sim_format_time(self,time):
         current_time = self.start_time + timedelta(minutes=time)
         return current_time.strftime("%H:%M") # This formats the time as hour:minute
    

    def format_in_hours_and_minutes(self, time):
        minutes = time / 60
        return f"{int(minutes) //60}h {int(minutes % 60)}m "

    def update_last_patient_time(self):
              self.last_patient_time = max(self.env.now, self.last_patient_time)
    
    #patient is the process
    def patient_generator(self, mean_interarrival_time, patient_spent_time):
        
        while True:
                interarrival_time= np.random.exponential(mean_interarrival_time)
                yield self.env.timeout(interarrival_time) 
                
                number_of_patients_arrival = max(1,np.random.poisson(1.5))
                for _ in range(number_of_patients_arrival):
                    self.patient_id+=1
                    print(f"Patient {self.patient_id} arrived at {self.sim_format_time(self.env.now)}")
                    self.env.process(self.patient_flow(patient_spent_time))
                
     #The stages of what the patient goes through
    def patient_flow(self,patient_spent_time):
        arrival_time=self.env.now #Records when the patient arrives
        yield self.env.process(self.patient_request_admission())
        
        priority=yield self.env.process(self.patient_request_nurse_for_risk_assesment())
        
        #If the patient is immediate, they are assigned to a bed 
        if priority == 0:
             print(f"Patient {self.patient_id} is immediate. Assigning a bed at {self.sim_format_time(self.env.now)}")
             yield self.env.process(self.patient_request_bed())
             yield self.env.process(self.patient_request_doctor_follow_up(priority))

        else:
             yield self.env.process(self.patient_request_doctor_for_doctor_consultation(priority))
        
        total_time_patient_spent = self.env.now - arrival_time
        patient_spent_time.append(total_time_patient_spent)
    

    def patient_request_admission(self):
         arrival_time = self.env.now
         print(f"Patient {self.patient_id} is waiting for a clerk at {self.sim_format_time(self.env.now)}")
         
         #Request general data in the reception 
         req = self.clerk.request()
         yield req 
         
         wait_time = self.env.now - arrival_time
         if wait_time > 0:
            self.patient_total_wait_time.append(wait_time)
         print(f"Patient {self.patient_id} was assigned a Clerk at {self.sim_format_time(self.env.now)}")

         #Stimulate the admission process
         yield self.env.timeout(random.randint(1,5))
         print(f"Patient {self.patient_id}'s admission completed at {self.sim_format_time(self.env.now)}")
         #aRelease the clerk
         self.clerk.release(req)
         print(f"Patient {self.patient_id}'s clerk released at {self.sim_format_time(self.env.now)}")
    
    
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



     
    def patient_request_nurse_for_risk_assesment (self):
            arrival_time= self.env.now
            #trying to make it  based on patient piriority 
            
            #Request a nurse for risk assessment
            req= self.nurse.request()
            yield req # Wait for the nurse to be availale
            
            wait_time = self.env.now - arrival_time
            if wait_time > 0:
                self.patient_total_wait_time.append(wait_time)
           
            print(f"Patient {self.patient_id} was assigned a nurse at at {self.sim_format_time(self.env.now)}")
            triage_category, priority = self.triage_manchester()
            print(f"Patient {self.patient_id} triaged as {triage_category} priority")


            #Simulate the risk assesment process time
            yield self.env.timeout(random.randint(1,5))
            #Release the nurse
            self.nurse.release(req)
            print(f"Patient {self.patient_id}'s nurse  was released at {self.sim_format_time(self.env.now)}")
            return priority
    
    def patient_gets_doctor(self):
        arrival_time= self.env.now
       
        #Request a doctor for the patient
        req = self.doctor.request()
        yield req # Wait for the doctor to be avaiable
        
        wait_time = self.env.now - arrival_time
        if wait_time > 0:
            self.patient_total_wait_time.append(wait_time)
        
        print(f"Patient {self.patient_id} was assigned a Doctor assigned at {self.sim_format_time(self.env.now)}")
        yield self.env.timeout(random.randint(1,5))
        print(f"Patient {self.patient_id}'s treatment completed at {self.sim_format_time(self.env.now)}")
        self.doctor.release(req)

    def update_bed_occupancy(self):
        self.track_bed_usage.append((self.env.now,self.occupied_beds))


    def patient_request_bed(self):
        arrival_time= self.env.now 
       
        #Request a bed for the patient
        req= self.bed.request()
        yield req # Waiit for a bed
        self.occupied_beds += 1
        wait_time = self.env.now - arrival_time
        if wait_time > 0:
            self.patient_total_wait_time.append(wait_time)
        print(f"Patient {self.patient_id} was  assigned to a bed at {self.sim_format_time(self.env.now)}")
        
        yield self.env.process(self.patient_gets_doctor())              

        #occupied_beds = self.bed.capacity - len(self.bed.queue)
        #self.track_bed_usage.append((self.env.now,occupied_beds))
        
        #Stimulate the length of stay (LOS) in the bed
        los = random.randint(30,120)
        yield self.env.timeout(los)
        self.update_last_patient_time()
        print(f"Patient {self.patient_id} has left the bed at {self.sim_format_time(self.env.now)}")

        self.occupied_beds-= 1
        self.bed.release(req)
        self.update_bed_occupancy()

        
        #This tracks when the user leaves the bed 
        #occupied_beds = self.bed.capacity - len(self.bed.queue)
        #self.track_bed_usage.append((self.env.now, occupied_beds))
        self.update_bed_occupancy()

        patient_LOS.append(los)


    def patient_request_doctor_for_doctor_consultation(self,priority):
         arrival_time = self.env.now
         if (priority > 0):
            #Request a doctor for consulation
            req = self.doctor.request(priority= priority)
            yield req # Wait for the doctor to be avavaible 
            wait_time = self.env.now - arrival_time
            if wait_time > 0:
                self.patient_total_wait_time.append(wait_time)
            print(f"Patient {self.patient_id} was assigned to a Doctor {self.patient_id} at{self.sim_format_time(self.env.now)}")
        
            #Stimulate the doctor consultation process 
            yield self.env.timeout(random.randint(1,5))
            print(f"Patient {self.patient_id}'s Doctor Consultation was completed at {self.sim_format_time(self.env.now)}")
            decision =random.uniform(0,1)
            
            if decision <0.5:
                self.update_last_patient_time()
                print(f"Patient {self.patient_id} is discharged at {self.sim_format_time(self.env.now)}")
                 #Release the doctor
                self.doctor.release(req)
                print(f"Patient {self.patient_id}'s Doctor released at {self.sim_format_time(self.env.now)}")
            elif decision<0.9:
               print(f"Patient {self.patient_id} needs to do tests")
               #Release the doctor
               self.doctor.release(req)
               print(f"Patient {self.patient_id}'s Doctor released at {self.sim_format_time(self.env.now)}")
               yield self.env.process(self.patient_request_tests(priority))
              
            else:
              print(f"Patient {self.patient_id} needs to take medication")
              #Release the doctor
              self.doctor.release(req)
              print(f"Patient {self.patient_id}'s Doctor released at {self.sim_format_time(self.env.now)}")
              yield self.env.process(self.patient_request_medication(priority))
         
     
    def patient_request_tests(self,priority):
     arrival_time = self.env.now
     req = self.nurse.request()
     yield req
     wait_time = self.env.now - arrival_time
     if wait_time > 0:
            self.patient_total_wait_time.append(wait_time)
     print(f"Patient {self.patient_id} was assigned to a Nurse at {self.sim_format_time(self.env.now)}")
     yield self.env.timeout(random.randint(1,5))
     print(f"Patient {self.patient_id} 's tests completed at {self.sim_format_time(self.env.now)}")
     self.nurse.release(req)
     print(f"Patient {self.patient_id}'s Nurse released at {self.sim_format_time(self.env.now)}")
     yield self.env.process(self.patient_request_doctor_follow_up(priority))

     

    def patient_request_medication(self,priority,):
        arrival_time = self.env.now
        req = self.nurse.request(priority= priority )
        yield req
        wait_time = self.env.now - arrival_time
        if wait_time > 0:
            self.patient_total_wait_time.append(wait_time)
        print(f"Patient {self.patient_id} was assigned to a Nurse at {self.sim_format_time(self.env.now)}")
        yield self.env.timeout(random.randint(1,5))
        print(f"Patient {self.patient_id}'s medication completed at {self.sim_format_time(self.env.now)}")
        self.nurse.release(req)
        print(f"Patient {self.patient_id}'s Nurse released at {self.sim_format_time(self.env.now)}")
        yield self.env.process(self.patient_request_doctor_follow_up(priority))


    def patient_request_doctor_follow_up(self,priority):
        arrival_time = self.env.now
        
        req= self.doctor.request(priority= priority)
        yield req
        
        wait_time = self.env.now - arrival_time
        if wait_time > 0:
            self.patient_total_wait_time.append(wait_time)
        
        print(f"Patient {self.patient_id} was assigned to a Doctor for a follow up at {self.sim_format_time(self.env.now)}")
        yield self.env.timeout(random.randint(1,5))
        print(f"Patient {self.patient_id}'s Doctor follow up completed at {self.sim_format_time(self.env.now)}")
        
        self.update_last_patient_time()
        print(f"Patient {self.patient_id} has left the A&E at {self.sim_format_time(self.env.now)}") 
        
        self.doctor.release(req)
        print(f"Patient {self.patient_id}'s Doctor released at {self.sim_format_time(self.env.now)}")

        
#Creates the simulation environmnment (A&E)
env = sp.Environment()
# Create the A&E department with resources
a_and_e = AnE(env, num_doctors=15, num_nurses=1, num_beds=65, num_clerk=4)
mean_interarrival_time=3
env.process(a_and_e.patient_generator(mean_interarrival_time, patient_spent_time))

env.run(until= 200) #This runs for 5000 minutes
until=200

#while any( resource.users for resource in [a_and_e.doctor, a_and_e.nurse, a_and_e.bed, a_and_e.clerk]):
    #env.step()
#while env.peek() < float("inf") and any(resource.users for resource in [a_and_e.doctor, a_and_e.nurse, a_and_e.clerk, a_and_e.bed]):
     #env.step()
#This to test if the  last patient has been processed fully 
print(f"Last patient {a_and_e.patient_id} left at {a_and_e.sim_format_time(a_and_e.last_patient_time)}")
print(f"Total patients seen: {a_and_e.patient_id}")

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

average_wait_time = sum(a_and_e.patient_total_wait_time) / len(a_and_e.patient_total_wait_time)

hours = int(average_wait_time // 60)
minutes = int(average_wait_time % 60)
print(f"The average wait time is {hours} hours and {minutes} minutes")











if len(a_and_e.patient_total_wait_time) > 0:
    average_waited_time = sum(a_and_e.patient_total_wait_time) / len(a_and_e.patient_total_wait_time)
    print(f"The average wait time is  { a_and_e.format_in_hours_and_minutes(average_waited_time)} for the pateints who waited")# Testing
else:
    # print("No waiting times recorded") Testing
     average_waited_time = 0

if a_and_e.patient_id>0:
     overall_average_time = sum(a_and_e.patient_total_wait_time) /  a_and_e.patient_id
     print(f"The overall average time is { a_and_e.format_in_hours_and_minutes(overall_average_time)} for all the patients") #Testing
else:
        ("No patient count recorded")
        overall_average_time = 0
print(a_and_e.track_bed_usage)
times,bed_count = zip(*a_and_e.track_bed_usage) # This  unpacks into two lists time and bed count 

#This graph is for bed occupancy over time 
plt.scatter(times, bed_count, marker="x", color="red")
plt.xlabel("Simulation Time in minutes")
plt.ylabel("Occupied Beds")
plt.title("Bed Occupancy Over Time")
plt.grid()
plt.xlim(0,until)
plt.ylim(0,a_and_e.bed.capacity)
plt.show()