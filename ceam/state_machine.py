# ~/ceam/ceam/state_machine.py

import pandas as pd
import numpy as np

from ceam.util import get_draw


class State:
    def __init__(self, state_id):
        self.state_id = state_id
        self.transition_set = TransitionSet()

    def next_state(self, agents, state_column):
        if len(self.transition_set) == 0:
            return agents

        groups = self.transition_set.groupby_new_state(agents)

        if groups:
            results = []
            for state, affected_agents in sorted(groups.items(), key=lambda x:str(x[0])):
                if state != 'null_transition':
                    results.append(state.transition_effect(affected_agents, state_column))
                else:
                    results.append(affected_agents)

            return pd.concat(results)
        return pd.DataFrame(columns=agents.columns)

    def transition_effect(self, agents, state_column):
        agents[state_column] = self.state_id
        agents = self._transition_side_effect(agents, state_column)
        return agents

    def _transition_side_effect(self, agents, state_column):
        return agents

    def __str__(self):
        return 'State("{0}" ...)'.format(self.state_id)


class TransitionSet(list):
    def __init__(self, allow_null_transition=True, *args, **kwargs):
        super(TransitionSet, self).__init__(*args, **kwargs)
        self.allow_null_transition = allow_null_transition

    def groupby_new_state(self, agents):
        outputs, probabilities = zip(*[(t.output, np.array(t.probability(agents))) for t in self])
        outputs = list(outputs)

        total = np.sum(probabilities, axis=0)
        if not self.allow_null_transition:
            probabilities /= total
        else:
            if np.any(total > 1):
                raise ValueError("Total transition probability greater than 1")
            else:
                probabilities = np.concatenate([probabilities, [(1-total)]])
                outputs.append('null_transition')

        draw = np.array(get_draw(agents))
        sums = probabilities.cumsum(axis=0)
        output_indexes = (draw >= sums).sum(axis=0)
        groups = agents.groupby(output_indexes)
        return {outputs[i]:sub_group for i, sub_group in groups}


class Transition:
    def __init__(self, output, probability_func=lambda agents: np.full(len(agents), 1, dtype=float)):
        self.output = output
        self.probability = probability_func

    def __str__(self):
        return 'Transition("{0}" ...)'.format(self.output.state_id)


class Machine:
    def __init__(self, state_column):
        self.states = list()
        self.state_column = state_column

    def transition(self, agents):
        #groups = agents.groupby(self.state_column, group_keys=False)
        #state_map = {state.state_id:state for state in self.states}
        #def transformer(agents):
        #    state = state_map[agents.iloc[0][self.state_column]]
        #    return state.next_state(agents, self.state_column)
        #return groups.apply(transformer)
        result = []
        for state in self.states:
            affected_agents = agents[agents[self.state_column] == state.state_id]
            result.append(state.next_state(affected_agents, self.state_column))
        return pd.concat(result)

    def to_dot(self):
        from graphviz import Digraph
        dot = Digraph(format='png')
        for state in self.states:
            dot.node(state.state_id)
            for transition in state.transition_set:
                dot.edge(state.state_id, transition.output.state_id)
        return dot


# End.