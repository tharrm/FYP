import simpy as sp
import random
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta


#Creates the simulation environment 
class AnE:
    
    def __init__(self, env, num_doctors, num_nurses, num_beds, num_clerk):
        self.env = env
        self.doctor = sp.PriorityResource(env, num_doctors)
        self.nurse = sp.PriorityResource(env, num_nurses)
        self.bed = sp.Resource(env, num_beds)
        self.clerk = sp.Resource(env, num_clerk) 
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
    def patient_generator(self, mean_interarrival_time):
        patient_ID = 0
        while True:
                interarrival_time= np.random.exponential(mean_interarrival_time)
                yield self.env.timeout(interarrival_time) 
                
                number_of_patients_arrival = max(1,np.random.poisson(1.5))
                for _ in range(number_of_patients_arrival):
                    self.patientCount +=1 
                    patient_ID+=1
                    self.active_patients.add(patient_ID)
                    print(f"Patient {patient_ID} arrived at {self.sim_format_time(self.env.now)}")
                    self.env.process(self.patient_flow(patient_ID))
                
     #The stages of what the patient goes through
    def patient_flow(self, patient_ID):
        arrival_time=self.env.now #Records when the patient arrives
        yield self.env.process(self.patient_request_admission(patient_ID))
        
        priority=yield self.env.process(self.patient_request_nurse_for_risk_assesment(patient_ID))
        
        #If the patient is immediate, they are assigned to a bed 
        if priority == 0:
             self.num_patient_immediate += 1
             print(f"Patient {patient_ID} is immediate. Assigning a bed at {self.sim_format_time(self.env.now)}")
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
        a_and_e.patient_spent_time.append(total_time_patient_spent)
        self.active_patients.remove(patient_ID)

    def patient_request_admission(self,patient_ID):
         arrival_time = self.env.now
         print(f"Patient {patient_ID} is waiting for a clerk at {self.sim_format_time(self.env.now)}")
         
         #Request general data in the reception 
         req = self.clerk.request()
         yield req 
         
         wait_time = self.env.now - arrival_time
         if wait_time > 0:
             self.track_waiting_time_for_clerk.append(wait_time)

         self.patient_total_wait_time.append(wait_time)
         if wait_time > 0:
            self.patient_who_waited.append(wait_time)
      

         print(f"Patient {patient_ID} was assigned a Clerk at {self.sim_format_time(self.env.now)}")

         #Stimulate the admission process
         yield self.env.timeout(random.randint(1,5))
         finish_time = self.env.now
         duration = finish_time - arrival_time
         self.track_time_admission.append(duration)
         print(f"Patient {patient_ID}'s admission completed at {self.sim_format_time(self.env.now)}")
         
         #aRelease the clerk
         self.clerk.release(req)
         print(f"Patient {patient_ID}'s clerk released at {self.sim_format_time(self.env.now)}")
    
    
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


           
            print(f"Patient {patient_ID} was assigned a nurse at at {self.sim_format_time(self.env.now)}")
            triage_category, priority = self.triage_manchester()
            print(f"Patient {patient_ID} triaged as {triage_category} priority")


            #Simulate the risk assesment process time
            yield self.env.timeout(random.randint(1,5))
            finish_time = self.env.now
            duration = finish_time - arrival_time
            self.track_time_risk_assessment.append(duration)
            #Release the nurse
            self.nurse.release(req)
            print(f"Patient {patient_ID}'s nurse  was released at {self.sim_format_time(self.env.now)}")
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
        
        
        print(f"Patient {patient_ID} was assigned a Doctor assigned at {self.sim_format_time(self.env.now)}")
        yield self.env.timeout(random.randint(1,5))
        finish_time = self.env.now
        duration = finish_time - arrival_time
        self.track_time_doctor_consultation.append(duration)
        
        print(f"Patient {patient_ID}'s treatment completed at {self.sim_format_time(self.env.now)}")
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

        print(f"Patient {patient_ID} was  assigned to a bed at {self.sim_format_time(self.env.now)}")
        
        yield self.env.process(self.patient_gets_doctor(patient_ID))              

        #occupied_beds = self.bed.capacity - len(self.bed.queue)
        #self.track_bed_usage.append((self.env.now,occupied_beds))
        
        #Stimulate the length of stay (LOS) in the bed
        los = random.randint(30,120)
        yield self.env.timeout(los)
        self.update_last_patient_time()
        print(f"Patient {patient_ID} has left the bed at {self.sim_format_time(self.env.now)}")

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
          

            print(f"Patient {patient_ID} was assigned to a Doctor at {self.sim_format_time(self.env.now)}")
        
            #Stimulate the doctor consultation process 
            yield self.env.timeout(random.randint(1,5))
            print(f"Patient {patient_ID}'s Doctor Consultation was completed at {self.sim_format_time(self.env.now)}")
            finish_time = self.env.now
            duration = finish_time - arrival_time
            self.track_time_doctor_consultation.append(duration)
            decision =random.uniform(0,1)
            
            if decision <0.5:
                self.track_time_for_discharge.append(duration)
                self.update_last_patient_time()
                print(f"Patient {patient_ID} is discharged at {self.sim_format_time(self.env.now)}")
                self.num_patient_discharged += 1
                

                 #Release the doctor
                self.doctor.release(req)
                print(f"Patient {patient_ID}'s Doctor released at {self.sim_format_time(self.env.now)}")
            elif decision<0.9:
               self.num_patient_requires_tests += 1
               print(f"Patient {patient_ID} needs to do tests")
               #Release the doctor
               self.doctor.release(req)
               print(f"Patient {patient_ID}'s Doctor released at {self.sim_format_time(self.env.now)}")
               yield self.env.process(self.patient_request_tests(patient_ID,priority))
              
            else:
              self.num_patient_requires_medication += 1
              print(f"Patient {patient_ID} needs to take medication")
              #Release the doctor
              self.doctor.release(req)
              print(f"Patient {patient_ID}'s Doctor released at {self.sim_format_time(self.env.now)}")
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

    
     print(f"Patient {patient_ID} was assigned to a Nurse at {self.sim_format_time(self.env.now)}")
     yield self.env.timeout(random.randint(1,5))
     
     finish_time = self.env.now
     duration = finish_time - arrival_time
     self.track_time_tests.append(duration)
    
     print(f"Patient {patient_ID} 's tests completed at {self.sim_format_time(self.env.now)}")
     self.nurse.release(req)
     print(f"Patient {patient_ID}'s Nurse released at {self.sim_format_time(self.env.now)}")
     yield self.env.process(self.patient_request_doctor_follow_up(patient_ID, priority))

     

    def patient_request_medication(self,patient_ID,priority):
        arrival_time = self.env.now
        req = self.nurse.request(priority= priority )
        yield req
        print(f"Patient {patient_ID} with priority {priority} was assigned to  a Nurse at {self.sim_format_time(self.env.now)}")
        wait_time = self.env.now - arrival_time
        self.patient_total_wait_time.append(wait_time)
        if wait_time > 0:
            self.patient_who_waited.append(wait_time)
            self.track_waiting_time_for_nurse.append(wait_time)

        print(f"Patient {patient_ID} was assigned to a Nurse at {self.sim_format_time(self.env.now)}")
        yield self.env.timeout(random.randint(1,5))
        print(f"Pateint {patient_ID} finished medication at {self.sim_format_time(self.env.now)}" )
        
        finish_time = self.env.now
        duration = finish_time - arrival_time
        #print(f"Duration " + duration)
        self.track_time_medication.append(duration)

        print(f"Patient {patient_ID}'s medication completed at {self.sim_format_time(self.env.now)}")
        self.nurse.release(req)
        print(f"Patient {patient_ID}'s Nurse released at {self.sim_format_time(self.env.now)}")
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
        
        print(f"Patient {patient_ID} was assigned to a Doctor for a follow up at {self.sim_format_time(self.env.now)}")
        yield self.env.timeout(random.randint(1,5))

        finish_time = self.env.now
        duration = finish_time - arrival_time
        self.track_time_for_follow_up.append(duration)

        print(f"Patient {patient_ID}'s Doctor follow up completed at {self.sim_format_time(self.env.now)}")
    
        self.update_last_patient_time()
        print(f"Patient {patient_ID} has left the A&E at {self.sim_format_time(self.env.now)}") 
        
        self.doctor.release(req)
        print(f"Patient {patient_ID}'s Doctor released at {self.sim_format_time(self.env.now)}")

        
#Creates the simulation environmnment (A&E)
env = sp.Environment()
# Create the A&E department with resources
a_and_e = AnE(env, num_doctors=10, num_nurses=10, num_beds=5, num_clerk=3)
mean_interarrival_time=3 # This lets user 
env.process(a_and_e.patient_generator(mean_interarrival_time))

env.run(until= 200) #This runs for 5000 minutes
until=200
#while env.peek() < until:
    #env.step()
while a_and_e.active_patients != set():
    env.step()

#while any( resource.users for resource in [a_and_e.doctor, a_and_e.nurse, a_and_e.bed, a_and_e.clerk]):
    #env.step()
#while env.peek() < float("inf") and any(resource.users for resource in [a_and_e.doctor, a_and_e.nurse, a_and_e.clerk, a_and_e.bed]):
    #env.step()
#This to test if the  last patient has been processed fully 
print(f"Last patient {a_and_e.patientCount} left at {a_and_e.sim_format_time(a_and_e.last_patient_time)}")
print(f"Total patients seen: {a_and_e.patientCount}")
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

average_wait_time = sum(a_and_e.patient_who_waited) / len(a_and_e.patient_who_waited)

hours = int(average_wait_time // 60)
minutes = int(average_wait_time % 60)
print(f"The average for patients who had to had wait time is {hours} hours and {minutes} minutes")


#This calculates the overall average wait time even with pateints who did not wait 
overall_average_time = sum(a_and_e.patient_total_wait_time) / len (a_and_e.patient_total_wait_time)

hours1= int(overall_average_time // 60)
minutes1= int(overall_average_time % 60)

print(f"The average  for the overall wait time is (pateints who also did not need to wait) {hours1} hours and {minutes1} minutes")


#print(a_and_e.track_bed_usage) Testing 
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

#This graph is for the time pateints spent in the AnE
plt.boxplot(a_and_e.patient_spent_time, vert=False, patch_artist = True, boxprops=dict(facecolor="red"))
plt.title("Time Patients Spent in A&E")
plt.xlabel("Time Patient Spent in A&E (minutes)")
plt.grid()
plt.show()

number_of_bins = int(np.sqrt(len(a_and_e.patient_who_waited)))
#This graph is for the average waiting time for patients

plt.hist(a_and_e.patient_who_waited, bins=number_of_bins, color="blue", edgecolor="black")
plt.title("Wait Time for Patients")
plt.xlabel("Wait Time (minutes)")
plt.ylabel("Frequency")
plt.grid()
plt.xlim(0,until)
plt.show()



plt.boxplot(a_and_e.patient_who_waited , vert=False, patch_artist=True, boxprops=dict(facecolor="blue"))
plt.title("Wait Time for Patients")
plt.xlabel("Wait Time (minutes)")
plt.xlim(0,until)
plt.grid()
plt.show()

# Average wait times for the resources 
average_resource_wait_time = [ np.mean(a_and_e.track_waiting_time_for_clerk),
                               np.mean(a_and_e.track_waiting_time_for_nurse),
                               np.mean(a_and_e.track_waiting_time_for_doctor),
                               np.mean(a_and_e.track_waiting_time_for_bed)
                              ]
resource_names = ["Clerk", "Nurse", "Doctor", "Bed"]
plt.bar(resource_names, average_resource_wait_time, color = "green" )
plt.title("Average Wait Time for Resoruces")
plt.xlabel("Resources")
plt.ylabel("Average Wait Time Minutes")
plt.grid(axis="y")
plt.show()

#Total wait time for the resources
resource_wait_time = [ sum(a_and_e.track_waiting_time_for_clerk),
                      sum(a_and_e.track_waiting_time_for_nurse),
                      sum(a_and_e.track_waiting_time_for_doctor),
                      sum(a_and_e.track_waiting_time_for_bed)
                 ]   

plt.bar(resource_names, resource_wait_time, color = "green" )
plt.title(" Wait Time for Resources")
plt.xlabel("Resources")
plt.ylabel("Wait Time (Minutes)")
plt.grid(axis="y")
plt.show()    

#Triage patients bar chart
max_y = (a_and_e.patientCount// 10 + 1) * 10 # Rounds up to the nearest 10
triage_categories = ["Immediate", "Very Urgent", "Urgent", "Standard", "Non-Urgent"]
plt.bar(triage_categories, [a_and_e.num_patient_immediate, a_and_e.num_patient_very_urgent, a_and_e.num_patient_urgent, a_and_e.num_patient_standard, a_and_e.num_patient_non_urgent], color="purple")
plt.title("Number of Patients in Triage Categories")
plt.ylabel("Number of Patients")
plt.xlabel("Triage Categories")
plt.grid(axis='y')
plt.yticks(range(0, max_y+ 1,10)) #Added +1 as rangee excludes the last number, the y scales goes up by 10
plt.show()

#Duration for the stages of the patient flow
average_time_for_stages = [np.mean(a_and_e.track_time_admission),
                           np.mean(a_and_e.track_time_risk_assessment),
                           np.mean(a_and_e.track_time_doctor_consultation),
                           np.mean(a_and_e.track_time_tests),
                           np.mean(a_and_e.track_time_medication),
                           np.mean(a_and_e.track_time_for_follow_up),
                           np.mean(a_and_e.track_time_for_discharge)]
stage_names = ["Admission", "Risk Assessment", "Doctor Consultation", "Tests", "Medication", "Follow Up", "Discharge"]
plt.bar(stage_names, average_time_for_stages, color="orange")
plt.title("Average Time for Stages of Patient Flow")
plt.xlabel("Stages")
plt.ylabel("Average Time (minutes)")
plt.grid(axis="y")
plt.show()
 
