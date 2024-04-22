"""
=========
Component
=========

A base Component class to be used to create components for use in ``vivarium``
simulations.
"""

import re
from abc import ABC
from inspect import signature
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loguru._logger import Logger

from vivarium.framework.event import Event

if TYPE_CHECKING:
    from vivarium.framework.engine import Builder
    from vivarium.framework.population import PopulationView, SimulantData


DEFAULT_EVENT_PRIORITY = 5
"""The default priority at which events will be triggered."""


class Component(ABC):
    """
    The base class for all components used in a Vivarium simulation.

    A `Component` in a Vivarium simulation represents a distinct feature or
    aspect of the model. It encapsulates the logic and data needed for that
    feature. Components commonly interact with the rest of the simulation by
    creating and updating columns in the state table, registering pipelines,
    and registering modifiers on pipelines created by other components. Observer
    components might also register observations. All components within a
    simulation must have a unique name, which is generated by default from the
    component's class and the argument passed to its constructor.

    The `setup_component` is run by Vivarium during the setup phase and performs
    a series of operations to prepare the component for the simulation. These
    operations include setting the logger for the component, calling the
    component's custom `setup` method, setting the population view if the
    component needs one, and registering listeners for each lifecycle event if
    the component has defined a method to be triggered on that event.

    Subclasses of `Component` should override these properties as needed:

    - `sub_components`
    - `configuration_defaults`
    - `columns_created`
    - `columns_required`
    - `initialization_requirements`
    - `population_view_query`
    - `post_setup_priority`
    - `time_step_prepare_priority`
    - `time_step_priority`
    - `time_step_cleanup_priority`
    - `collect_metrics_priority`
    - `simulation_end_priority`

    Subclasses of `Component` should override these methods in order to have
    operations occur during the appropriate lifecycle phase of a simulation:

    - `setup`
    - `on_post_setup`
    - `on_initialize_simulants`
    - `on_time_step_prepare`
    - `on_time_step`
    - `on_time_step_cleanup`
    - `on_collect_metrics`
    - `on_simulation_end`
    """

    @staticmethod
    def build_lookup_table_config(
        value: str,
        continuous_columns: List[str] = [],
        categorical_columns: List[str] = [],
        key_name: str = None,
        **kwargs: Dict[str, Any],
    ) -> dict:
        config = {
            "value": value,
            "continuous_columns": continuous_columns,
            "categorical_columns": categorical_columns,
        }
        if key_name:
            config["key_name"] = key_name
        config.update(kwargs)
        return config

    CONFIGURATION_DEFAULTS: Dict[str, Any] = {}
    """
    A dictionary containing the defaults for any configurations managed by this
    component. An empty dictionary indicates no managed configurations.
    """

    def __repr__(self):
        """
        Returns a string representation of the __init__ call made to create this
        object.

        The representation is built by retrieving the initialization parameters
        and their values. If a value is an instance of Component, its own
        __repr__() is called. The resulting string is stored in the _repr
        attribute and returned.

        IMPORTANT: this method must not be called within the `__init__`
        functions of this component or its subclasses or its value may not be
        initialized correctly.

        Returns
        -------
        str
            A string representation of the __init__ call made to create this
            object.
        """
        if not self._repr:
            args = [
                f"{name}={value.__repr__() if isinstance(value, Component) else value}"
                for name, value in self.get_initialization_parameters().items()
            ]
            args = ", ".join(args)
            self._repr = f"{type(self).__name__}({args})"

        return self._repr

    def __str__(self):
        return self._repr

    ##############
    # Properties #
    ##############

    @property
    def name(self) -> str:
        """
        Returns the name of the component. By convention, these are in snake
        case with arguments of the `__init__` appended and separated by `.`.

        Names must be unique within a simulation.

        The name is created by first converting the name of the class to snake
        case. Then, the names of the initialization parameters are appended,
        separated by `.`. If a parameter is an instance of Component, its name
        property is used; otherwise, the string representation of the parameter
        is used. The resulting string is stored in the _name attribute and
        returned.

        IMPORTANT: this property must not be accessed within the `__init__`
        functions of this component or its subclasses or its value may not be
        initialized correctly.

        Returns
        -------
        str
            The unique name of the component.
        """
        if not self._name:
            base_name = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", type(self).__name__)
            base_name = re.sub("([a-z0-9])([A-Z])", r"\1_\2", base_name).lower()

            args = [
                f"'{value.name}'" if isinstance(value, Component) else str(value)
                for value in self.get_initialization_parameters().values()
            ]
            self._name = ".".join([base_name] + args)

        return self._name

    @property
    def sub_components(self) -> List["Component"]:
        """
        Provide components managed by this component.

        Returns
        -------
        List[Component]
            A list of components that are managed by this component.
        """
        return self._sub_components

    @property
    def configuration_defaults(self) -> Dict[str, Any]:
        """
        Provides a dictionary containing the defaults for any configurations
        managed by this component.

        These default values will be stored at the `component_configs` layer of the
        simulation's LayeredConfigTree.

        Returns
        -------
        Dict[str, Any]
            A dictionary containing the defaults for any configurations managed by
            this component.
        """
        return self.CONFIGURATION_DEFAULTS

    @property
    def columns_created(self) -> List[str]:
        """
        Provides names of columns created by the component.

        Returns
        -------
        List[str]
            Names of the columns created by this component, or an empty list if
            none.
        """
        return []

    @property
    def columns_required(self) -> Optional[List[str]]:
        """
        Provides names of columns required by the component.

        Returns
        -------
        Optional[List[str]]
            Names of required columns not created by this component. An empty
            list means all available columns are needed. `None` means no
            additional columns are necessary.
        """
        return None

    @property
    def standard_lookup_tables(self) -> List[str]:
        """
        Returns a list of keys that are used to create standard lookup tables in a component.
        """
        return []

    @property
    def initialization_requirements(self) -> Dict[str, List[str]]:
        """
        Provides the names of all values required by this component during
        simulant initialization.

        Returns
        -------
        Dict[str, List[str]]
            A dictionary containing the additional requirements of this
            component during simulant initialization. An omitted key or an empty
            list for a key implies no requirements for that key during
            initialization.
        """
        return {
            "requires_columns": [],
            "requires_values": [],
            "requires_streams": [],
        }

    @property
    def population_view_query(self) -> Optional[str]:
        """
        Provides a query to use when filtering the component's `PopulationView`.

        Returns
        -------
        Optional[str]
            A pandas query string for filtering the component's `PopulationView`.
            Returns `None` if no filtering is required.
        """
        return None

    @property
    def post_setup_priority(self) -> int:
        """
        Provides the priority of this component's post_setup listener.

        Returns
        -------
        int
            The priority of this component's post_setup listener. This value
            can range from 0 to 9, inclusive.
        """
        return DEFAULT_EVENT_PRIORITY

    @property
    def time_step_prepare_priority(self) -> int:
        """
        Provides the priority of this component's time_step__prepare listener.

        Returns
        -------
        int
            The priority of this component's time_step__prepare listener. This value
            can range from 0 to 9, inclusive.
        """
        return DEFAULT_EVENT_PRIORITY

    @property
    def time_step_priority(self) -> int:
        """
        Provides the priority of this component's time_step listener.

        Returns
        -------
        int
            The priority of this component's time_step listener. This value
            can range from 0 to 9, inclusive.
        """
        return DEFAULT_EVENT_PRIORITY

    @property
    def time_step_cleanup_priority(self) -> int:
        """
        Provides the priority of this component's time_step__cleanup listener.

        Returns
        -------
        int
            The priority of this component's time_step__cleanup listener. This value
            can range from 0 to 9, inclusive.
        """
        return DEFAULT_EVENT_PRIORITY

    @property
    def collect_metrics_priority(self) -> int:
        """
        Provides the priority of this component's collect_metrics listener.

        Returns
        -------
        int
            The priority of this component's collect_metrics listener. This value
            can range from 0 to 9, inclusive.
        """
        return DEFAULT_EVENT_PRIORITY

    @property
    def simulation_end_priority(self) -> int:
        """
        Provides the priority of this component's simulation_end listener.

        Returns
        -------
        int
            The priority of this component's simulation_end listener. This value
            can range from 0 to 9, inclusive.
        """
        return DEFAULT_EVENT_PRIORITY

    #####################
    # Lifecycle methods #
    #####################

    def __init__(self):
        """
        Initializes a new instance of the Component class.

        This method is the initializer for the Component class. It initializes
        logger of type Logger and population_view of type PopulationView to None.
        These attributes will be fully initialized in the setup_component method
        of this class.
        """
        self._repr: str = ""
        self._name: str = ""
        self._sub_components: List["Component"] = []
        self.logger: Optional[Logger] = None
        self.population_view: Optional[PopulationView] = None
        self.lookup_tables = {}

    def setup_component(self, builder: "Builder") -> None:
        """
        Sets up the component for a Vivarium simulation.

        This method is run by Vivarium during the setup phase. It performs a series
        of operations to prepare the component for the simulation.

        It sets the logger for the component, sets up the component, sets the
        population view, and registers various listeners including post_setup,
        simulant_initializer, time_step_prepare, time_step, time_step_cleanup,
        collect_metrics, and simulation_end listeners.

        Parameters
        ----------
        builder : Builder
            The builder object used to set up the component.

        Returns
        -------
        None
        """
        self.logger = builder.logging.get_logger(self.name)
        self.build_lookup_tables(builder)
        self.setup(builder)
        self._set_population_view(builder)
        self._register_post_setup_listener(builder)
        self._register_simulant_initializer(builder)
        self._register_time_step_prepare_listener(builder)
        self._register_time_step_listener(builder)
        self._register_time_step_cleanup_listener(builder)
        self._register_collect_metrics_listener(builder)
        self._register_simulation_end_listener(builder)

    #######################
    # Methods to override #
    #######################

    def setup(self, builder: "Builder") -> None:
        """
        Defines custom actions this component needs to run during the setup
        lifecycle phase.

        This method is intended to be overridden by subclasses to perform any
        necessary setup operations specific to the component. By default, it
        does nothing.

        Parameters
        ----------
        builder : Builder
            The builder object used to set up the component.

        Returns
        -------
        None
        """
        pass

    def on_post_setup(self, event: Event) -> None:
        """
        Method that vivarium will run during the post_setup event.

        This method is intended to be overridden by subclasses if there are
        operations they need to perform specifically during the post_setup event.

        NOTE: This method is not commonly used functionality.

        Parameters
        ----------
        event : Event
            The event object associated with the post_setup event.

        Returns
        -------
        None
        """
        pass

    def on_initialize_simulants(self, pop_data: "SimulantData") -> None:
        """
        Method that vivarium will run during simulant initialization.

        This method is intended to be overridden by subclasses if there are
        operations they need to perform specifically during the simulant
        initialization phase.

        Parameters
        ----------
        pop_data : SimulantData
            The data associated with the simulants being initialized.

        Returns
        -------
        None
        """
        pass

    def on_time_step_prepare(self, event: Event) -> None:
        """
        Method that vivarium will run during the time_step__prepare event.

        This method is intended to be overridden by subclasses if there are
        operations they need to perform specifically during the
        time_step__prepare event.

        Parameters
        ----------
        event : Event
            The event object associated with the time_step__prepare event.

        Returns
        -------
        None
        """
        pass

    def on_time_step(self, event: Event) -> None:
        """
        Method that vivarium will run during the time_step event.

        This method is intended to be overridden by subclasses if there are
        operations they need to perform specifically during the time_step event.

        Parameters
        ----------
        event : Event
            The event object associated with the time_step event.

        Returns
        -------
        None
        """
        pass

    def on_time_step_cleanup(self, event: Event) -> None:
        """
        Method that vivarium will run during the time_step__cleanup event.

        This method is intended to be overridden by subclasses if there are
        operations they need to perform specifically during the
        time_step__cleanup event.

        Parameters
        ----------
        event : Event
            The event object associated with the time_step__cleanup event.

        Returns
        -------
        None
        """
        pass

    def on_collect_metrics(self, event: Event) -> None:
        """
        Method that vivarium will run during the collect_metrics event.

        This method is intended to be overridden by subclasses if there are
        operations they need to perform specifically during the collect_metrics
        event.

        Parameters
        ----------
        event : Event
            The event object associated with the collect_metrics event.

        Returns
        -------
        None
        """
        pass

    def on_simulation_end(self, event: Event) -> None:
        """
        Method that vivarium will run during the simulation_end event.

        This method is intended to be overridden by subclasses if there are
        operations they need to perform specifically during the simulation_end
        event.

        Parameters
        ----------
        event : Event
            The event object associated with the simulation_end event.

        Returns
        -------
        None
        """
        pass

    ##################
    # Helper methods #
    ##################

    def get_initialization_parameters(self) -> Dict[str, Any]:
        """
        Retrieves the values of all parameters specified in the `__init__` that
        have an attribute with the same name.

        Note: this retrieves the value of the attribute at the time of calling,
        which is not guaranteed to be the same as the original value.

        Returns
        -------
        dict
            A dictionary where the keys are the names of the parameters used in
            the `__init__` method and the values are their current values.

        """
        return {
            parameter_name: getattr(self, parameter_name)
            for parameter_name in signature(self.__init__).parameters
            if hasattr(self, parameter_name)
        }

    def build_lookup_tables(self, builder: "Builder") -> None:
        """
        Method to create standard lookup tables for the component. This will create a
        lookup table for each lookup key in self.standard_lookup_tables property. If
        additional lookup tables are desired, users have, users have two options: (1)
        override this method by calling the super method and adding them, or
        (2) overriding the standard 'lookup_tables' property.
        """
        for lookup_table_name in self.standard_lookup_tables:
            lookup_table_config = builder.configuration[self.name][lookup_table_name]
            # TODO: make path to configuration the data key when we align artifact
            # keys with configuration path
            if lookup_table_config["value"] == "data":
                table = builder.lookup.build_table(
                    data=builder.data.load(lookup_table_config["key_name"]),
                    key_columns=lookup_table_config["categorical_columns"],
                    parameter_columns=lookup_table_config["continuous_columns"],
                )
            else:
                table = builder.lookup.build_table(lookup_table_config["value"])
            self.lookup_tables[lookup_table_name] = table

    def _set_population_view(self, builder: "Builder") -> None:
        """
        Creates the PopulationView for this component if it needs access to
        the state table.

        The method determines the necessary columns for the PopulationView
        based on the columns required and created by this component. If no
        columns are required or created, no PopulationView is set.

        Parameters
        ----------
        builder : Builder
            The builder object used to set up the component.

        Returns
        -------
        None
        """
        if self.columns_required:
            # Get all columns created and required
            population_view_columns = self.columns_created + self.columns_required
        elif self.columns_required == []:
            # Empty list means population view needs all available columns
            population_view_columns = []
        elif self.columns_required is None and self.columns_created:
            # No additional columns required, so just get columns created
            population_view_columns = self.columns_created
        else:
            # no need for a population view if no columns created or required
            population_view_columns = None

        if population_view_columns is not None:
            self.population_view = builder.population.get_view(
                population_view_columns, self.population_view_query
            )

    def _register_post_setup_listener(self, builder: "Builder") -> None:
        """
        Registers a post_setup listener if this component has defined one.

        This method allows the component to respond to "post_setup" events if it
        has its own `on_post_setup` method. The listener will be registered with
        the component's post_setup priority, allowing control over the order of
        operations when multiple components are listening to the same event.

        Parameters
        ----------
        builder : Builder
            The builder with which to register the listener.

        Returns
        -------
        None
        """
        if type(self).on_post_setup != Component.on_post_setup:
            builder.event.register_listener(
                "post_setup",
                self.on_post_setup,
                self.post_setup_priority,
            )

    def _register_simulant_initializer(self, builder: "Builder") -> None:
        """
        Registers a simulant initializer if this component has defined one.

        This method allows the component to initialize simulants if it has its
        own `on_initialize_simulants` method. It registers this method with the
        builder's `PopulationManager``. It also specifies the columns that the
        component creates and any additional requirements for initialization.

        Parameters
        ----------
        builder : Builder
            The builder with which to register the initializer.

        Returns
        -------
        None
        """
        if type(self).on_initialize_simulants != Component.on_initialize_simulants:
            builder.population.initializes_simulants(
                self.on_initialize_simulants,
                creates_columns=self.columns_created,
                **self.initialization_requirements,
            )

    def _register_time_step_prepare_listener(self, builder: "Builder") -> None:
        """
        Registers a time_step_prepare listener if this component has defined one.

        This method allows the component to respond to "time_step_prepare" events
        if it has its own `on_time_step_prepare` method. The listener will be
        registered with the component's time_step_prepare priority.

        Parameters
        ----------
        builder : Builder
            The builder with which to register the listener.

        Returns
        -------
        None
        """
        if type(self).on_time_step_prepare != Component.on_time_step_prepare:
            builder.event.register_listener(
                "time_step__prepare",
                self.on_time_step_prepare,
                self.time_step_prepare_priority,
            )

    def _register_time_step_listener(self, builder: "Builder") -> None:
        """
        Registers a time_step listener if this component has defined one.

        This method allows the component to respond to "time_step" events
        if it has its own `on_time_step` method. The listener will be
        registered with the component's time_step priority.

        Parameters
        ----------
        builder : Builder
            The builder with which to register the listener.

        Returns
        -------
        None
        """
        if type(self).on_time_step != Component.on_time_step:
            builder.event.register_listener(
                "time_step",
                self.on_time_step,
                self.time_step_priority,
            )

    def _register_time_step_cleanup_listener(self, builder: "Builder") -> None:
        """
        Registers a time_step_cleanup listener if this component has defined one.

        This method allows the component to respond to "time_step_cleanup" events
        if it has its own `on_time_step_cleanup` method. The listener will be
        registered with the component's time_step_cleanup priority.

        Parameters
        ----------
        builder : Builder
            The builder with which to register the listener.

        Returns
        -------
        None
        """
        if type(self).on_time_step_cleanup != Component.on_time_step_cleanup:
            builder.event.register_listener(
                "time_step__cleanup",
                self.on_time_step_cleanup,
                self.time_step_cleanup_priority,
            )

    def _register_collect_metrics_listener(self, builder: "Builder") -> None:
        """
        Registers a collect_metrics listener if this component has defined one.

        This method allows the component to respond to "collect_metrics" events
        if it has its own `on_collect_metrics` method. The listener will be
        registered with the component's collect_metrics priority.

        Parameters
        ----------
        builder : Builder
            The builder with which to register the listener.

        Returns
        -------
        None
        """
        if type(self).on_collect_metrics != Component.on_collect_metrics:
            builder.event.register_listener(
                "collect_metrics",
                self.on_collect_metrics,
                self.collect_metrics_priority,
            )

    def _register_simulation_end_listener(self, builder: "Builder") -> None:
        """
        Registers a simulation_end listener if this component has defined one.

        This method allows the component to respond to "simulation_end" events
        if it has its own `on_simulation_end` method. The listener will be
        registered with the component's simulation_end priority.

        Parameters
        ----------
        builder : Builder
            The builder with which to register the listener.

        Returns
        -------
        None
        """
        if type(self).on_simulation_end != Component.on_simulation_end:
            builder.event.register_listener(
                "simulation_end",
                self.on_simulation_end,
                self.simulation_end_priority,
            )
