from datetime import datetime, timedelta
from time import time
from collections import defaultdict

import pandas as pd

from ceam.engine import Simulation, SimulationModule
from ceam.util import only_living
from ceam.modules.ihd import IHDModule
from ceam.modules.healthcare_access import HealthcareAccessModule
from ceam.modules.blood_pressure import BloodPressureModule
from ceam.modules.metrics import MetricsModule

def _hypertensive_categories(mask, population):
        under_60 = mask & (population.age < 60)
        over_60 = mask & (population.age >= 60)

        normotensive = under_60 & (population.systolic_blood_pressure < 140)
        normotensive |= over_60 & (population.systolic_blood_pressure < 150)

        hypertensive = under_60 & (population.systolic_blood_pressure >= 140) & (population.systolic_blood_pressure < 180)
        hypertensive |= over_60 & (population.systolic_blood_pressure >= 150) & (population.systolic_blood_pressure < 180)

        severe_hypertension = mask & (population.systolic_blood_pressure >= 180)

        return (normotensive, hypertensive, severe_hypertension)

class OpportunisticScreeningModule(SimulationModule):
    DEPENDS = (BloodPressureModule, HealthcareAccessModule,)

    def setup(self):
        self.cost_by_year = defaultdict(int)
        self.register_event_listener(self.non_followup_blood_pressure_test, 'general_healthcare_access')
        self.register_event_listener(self.followup_blood_pressure_test, 'followup_healthcare_access')
        self.register_event_listener(self.track_monthly_cost, 'time_step')
        self.register_event_listener(self.adjust_blood_pressure, 'time_step')

    def load_population_columns(self, path_prefix, population_size):
        #TODO: Some people will start out taking medications?
        self.population_columns = pd.DataFrame({
            'taking_blood_pressure_medication_a': [False]*population_size,
            'taking_blood_pressure_medication_b': [False]*population_size,
            })

    def non_followup_blood_pressure_test(self, label, mask, simulation):
        self.cost_by_year[simulation.current_time.year] += sum(mask) * 3.0

        #TODO: testing error

        normotensive, hypertensive, severe_hypertension = _hypertensive_categories(mask, simulation.population)

        # Normotensive simulants get a 60 month followup and no drugs
        simulation.population.loc[normotensive, 'healthcare_followup_date'] = simulation.current_time + timedelta(days= 30.5*60) # 60 months

        # Hypertensive simulants get a 1 month followup and no drugs
        simulation.population.loc[hypertensive, 'healthcare_followup_date'] = simulation.current_time + timedelta(days= 30.5) # 1 month

        # Severe hypertensive simulants get a 1 month followup and all drugs
        simulation.population.loc[severe_hypertension, 'healthcare_followup_date'] = simulation.current_time + timedelta(days= 30.5*6) # 6 months
        simulation.population.loc[severe_hypertension, 'taking_blood_pressure_medication_a'] = True
        simulation.population.loc[severe_hypertension, 'taking_blood_pressure_medication_b'] = True

    def followup_blood_pressure_test(self, label, mask, simulation):
        self.cost_by_year[simulation.current_time.year] += sum(mask) * 3.0

        normotensive, hypertensive, severe_hypertension = _hypertensive_categories(mask, simulation.population)

        nonmedicated_normotensive = normotensive & (simulation.population.taking_blood_pressure_medication_a == False) & (simulation.population.taking_blood_pressure_medication_b == False)
        medicated_normotensive = normotensive & ((simulation.population.taking_blood_pressure_medication_a == False) | (simulation.population.taking_blood_pressure_medication_b == False))

        # Unmedicated normotensive simulants get a 60 month followup
        simulation.population.loc[nonmedicated_normotensive, 'healthcare_followup_date'] = simulation.current_time + timedelta(days= 30.5*60) # 60 months

        # Medicated normotensive simulants drop their drugs and get an 11 month followup
        simulation.population.loc[medicated_normotensive, 'healthcare_followup_date'] = simulation.current_time + timedelta(days= 30.5*11) # 11 months
        simulation.population.loc[medicated_normotensive, 'taking_blood_pressure_medication_a'] = False
        simulation.population.loc[medicated_normotensive, 'taking_blood_pressure_medication_b'] = False

        # Hypertensive simulants get a 6 month followup and go on one drug
        # TODO: what if they are already taking drugs?
        simulation.population.loc[hypertensive, 'healthcare_followup_date'] = simulation.current_time + timedelta(days= 30.5*6) # 6 months
        simulation.population.loc[hypertensive, 'taking_blood_pressure_medication_a'] = True

        # Severe hypertensive simulants get the same treatment as during a non-followup test
        # TODO: is this right?
        simulation.population.loc[severe_hypertension, 'healthcare_followup_date'] = simulation.current_time + timedelta(days= 30.5*6) # 6 months
        simulation.population.loc[severe_hypertension, 'taking_blood_pressure_medication_a'] = True
        simulation.population.loc[severe_hypertension, 'taking_blood_pressure_medication_b'] = True

    @only_living
    def track_monthly_cost(self, label, mask, simulation):
        #TODO: realistic costs
        #TODO: Also, costs should be configured in some way other than magic constants in the code
        self.cost_by_year[simulation.current_time.year] += sum(mask & (simulation.population.taking_blood_pressure_medication_a == True)) * 1*simulation.last_time_step.days 
        self.cost_by_year[simulation.current_time.year] += sum(mask & (simulation.population.taking_blood_pressure_medication_b == True)) * 3*simulation.last_time_step.days 

    @only_living
    def adjust_blood_pressure(self, label, mask, simulation):
        # TODO: Real drug effects + adherance rates
        simulation.population.loc[mask & (simulation.population.taking_blood_pressure_medication_a == True)].systolic_blood_pressure -= 0.01
        simulation.population.loc[mask & (simulation.population.taking_blood_pressure_medication_b == True)].systolic_blood_pressure -= 0.01


def main():
    simulation = Simulation()

    modules = [IHDModule(), HealthcareAccessModule(), BloodPressureModule()]
    metrics_module = MetricsModule()
    modules.append(metrics_module)
    screening_module = OpportunisticScreeningModule()
    modules.append(screening_module)
    for module in modules:
        module.setup()
    simulation.register_modules(modules)

    simulation.load_population('/home/j/Project/Cost_Effectiveness/dev/data_processed/population_columns')
    simulation.load_data('/home/j/Project/Cost_Effectiveness/dev/data_processed')
    
    for i in range(10):
        start = time()
        simulation.run(datetime(1990, 1, 1), datetime(2013, 12, 31), timedelta(days=30.5)) #TODO: Is 30.5 days a good enough approximation of one month? -Alec
        print('YLDs: %s'%sum(simulation.yld_by_year.values()))
        print('Cost: %s'%sum(screening_module.cost_by_year.values()))
        print(metrics_module.metrics)
        print('Duration: %s'%(time()-start))
        simulation.reset()


if __name__ == '__main__':
    main()
