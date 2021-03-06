"""Economy underlying the BLP model."""

import abc
import collections
import functools
from typing import Dict, Hashable, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..configurations.formulation import ColumnFormulation, Formulation
from ..utilities.basics import Array, RecArray, StringRepresentation, TableFormatter


class Economy(abc.ABC, StringRepresentation):
    """An abstract economy underlying the BLP model."""

    product_formulations: Sequence[Optional[Formulation]]
    agent_formulation: Optional[Formulation]
    products: RecArray
    agents: RecArray
    unique_market_ids: Array
    unique_nesting_ids: Array
    N: int
    T: int
    K1: int
    K2: int
    K3: int
    D: int
    MD: int
    MS: int
    ED: int
    ES: int
    H: int
    _product_market_indices: Dict[Hashable, Array]
    _agent_market_indices: Dict[Hashable, Array]
    _max_J: int
    _max_I: int
    _X1_formulations: Tuple[ColumnFormulation, ...]
    _X2_formulations: Tuple[ColumnFormulation, ...]
    _X3_formulations: Tuple[ColumnFormulation, ...]
    _demographics_formulations: Tuple[ColumnFormulation, ...]
    _absorb_demand_ids: Optional[functools.partial]
    _absorb_supply_ids: Optional[functools.partial]

    @abc.abstractmethod
    def __init__(
            self, product_formulations: Sequence[Optional[Formulation]], agent_formulation: Optional[Formulation],
            products: RecArray, agents: RecArray) -> None:
        """Store information about formulations and data. Any fixed effects should be absorbed after initialization."""

        # store formulations and data
        self.product_formulations = product_formulations
        self.agent_formulation = agent_formulation
        self.products = products
        self.agents = agents

        # identify unique markets and nests
        self.unique_market_ids = np.unique(self.products.market_ids).flatten()
        self.unique_nesting_ids = np.unique(self.products.nesting_ids).flatten()

        # count dimensions
        self.N = self.products.shape[0]
        self.T = self.unique_market_ids.size
        self.K1 = self.products.X1.shape[1]
        self.K2 = self.products.X2.shape[1]
        self.K3 = self.products.X3.shape[1]
        self.D = self.agents.demographics.shape[1]
        self.MD = self.products.ZD.shape[1]
        self.MS = self.products.ZS.shape[1]
        self.ED = self.products.demand_ids.shape[1]
        self.ES = self.products.supply_ids.shape[1]
        self.H = self.unique_nesting_ids.size

        # identify market indices
        self._product_market_indices = {t: np.where(self.products.market_ids.flat == t) for t in self.unique_market_ids}
        self._agent_market_indices = {t: np.where(self.agents.market_ids.flat == t) for t in self.unique_market_ids}

        # identify the largest number of products and agents in a market
        self._max_J = max(v[0].size for v in self._product_market_indices.values())
        self._max_I = max(v[0].size for v in self._agent_market_indices.values())

        # identify column formulations
        self._X1_formulations = self.products.dtype.fields['X1'][2]
        self._X2_formulations = self.products.dtype.fields['X2'][2]
        self._X3_formulations = self.products.dtype.fields['X3'][2]
        self._demographics_formulations = self.agents.dtype.fields['demographics'][2]

        # construct fixed effect absorption functions
        self._absorb_demand_ids = self._absorb_supply_ids = None
        if self.ED > 0:
            assert product_formulations[0] is not None
            self._absorb_demand_ids = functools.partial(product_formulations[0]._build_absorb(self.products.demand_ids))
        if self.ES > 0:
            assert product_formulations[2] is not None
            self._absorb_supply_ids = functools.partial(product_formulations[2]._build_absorb(self.products.supply_ids))

    def __str__(self) -> str:
        """Format economy information as a string."""

        # associate dimensions and formulations with names
        dimension_mapping = collections.OrderedDict([
            ("N", self.N),
            ("T", self.T),
            ("K1", self.K1),
            ("K2", self.K2),
            ("K3", self.K3),
            ("D", self.D),
            ("MD", self.MD),
            ("MS", self.MS),
            ("ED", self.ED),
            ("ES", self.ES),
            ("H", self.H)
        ])
        formulation_mapping = collections.OrderedDict([
            ("X1: Linear Characteristics", self._X1_formulations),
            ("X2: Nonlinear Characteristics", self._X2_formulations),
            ("X3: Cost Characteristics", self._X3_formulations),
            ("d: Demographics", self._demographics_formulations)
        ])

        # build a dimensions section
        dimension_widths = [max(len(k) + 2, len(str(d))) for k, d in dimension_mapping.items() if d > 0]
        dimension_formatter = TableFormatter(dimension_widths)
        dimension_section = [
            "Dimensions:",
            dimension_formatter.line(),
            dimension_formatter([k for k, d in dimension_mapping.items() if d > 0], underline=True),
            dimension_formatter([d for k, d in dimension_mapping.items() if d > 0]),
            dimension_formatter.line()
        ]

        # build a formulations section
        formulation_header = ["Column Indices:"]
        formulation_widths = [max(len(formulation_header[0]), max(map(len, formulation_mapping.keys())))]
        for index in range(max(map(len, formulation_mapping.values()))):
            formulation_header.append(str(index))
            column_width = 5
            for formulation in formulation_mapping.values():
                if len(formulation) > index:
                    column_width = max(column_width, len(str(formulation[index])))
            formulation_widths.append(column_width)
        formulation_formatter = TableFormatter(formulation_widths)
        formulation_section = [
            "Formulations:",
            formulation_formatter.line(),
            formulation_formatter(formulation_header, underline=True)
        ]
        for name, formulations in formulation_mapping.items():
            if formulations:
                formulation_section.append(formulation_formatter([name] + list(map(str, formulations))))
        formulation_section.append(formulation_formatter.line())

        # combine the sections into one string
        return "\n\n".join("\n".join(s) for s in [dimension_section, formulation_section])

    def _validate_name(self, name: str) -> None:
        """Validate that a name corresponds to a variable in X1, X2, or X3."""
        formulations = self._X1_formulations + self._X2_formulations + self._X3_formulations
        names = {n for f in formulations for n in f.names}
        if name not in names:
            raise NameError(f"The name '{name}' is not one of the underlying variables, {list(sorted(names))}.")

    def _validate_firms_index(self, firms_index: int) -> None:
        """Validate a firm IDs index."""
        max_firms_index = self.products.firm_ids.shape[1]
        if not isinstance(firms_index, int) or not 0 <= firms_index <= max_firms_index:
            raise ValueError(f"firms_index must be an int between 0 and {firms_index}.")

    def _compute_true_X1(self, data_override: Optional[Mapping] = None, index: Optional[Array] = None) -> Array:
        """Compute X1 or columns of X1 without any absorbed demand-side fixed effects."""
        if index is None:
            index = np.ones(self.K1, np.bool)
        if self.ED == 0 and not data_override:
            return self.products.X1[:, index]
        columns = []
        for include, formulation in zip(index, self._X1_formulations):
            if include:
                columns.append(np.broadcast_to(formulation.evaluate(self.products, data_override), (self.N, 1)))
        return np.column_stack(columns)

    def _compute_true_X3(
            self, data_override: Optional[Mapping] = None, index: Optional[Array] = None) -> Array:
        """Compute X3 or columns of X3 without any absorbed supply-side fixed effects."""
        if index is None:
            index = np.ones(self.K3, np.bool)
        if self.ES == 0 and not data_override:
            return self.products.X3[:, index]
        columns = []
        for include, formulation in zip(index, self._X3_formulations):
            if include:
                columns.append(formulation.evaluate(self.products, data_override) * np.ones((self.N, 1)))
        return np.column_stack(columns)
