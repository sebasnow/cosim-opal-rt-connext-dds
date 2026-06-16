
# WARNING: THIS FILE IS AUTO-GENERATED. DO NOT MODIFY.

# This file was generated from CoSimTypes.idl
# using RTI Code Generator (rtiddsgen) version 4.5.0.
# The rtiddsgen tool is part of the RTI Connext DDS distribution.
# For more information, type 'rtiddsgen -help' at a command shell
# or consult the Code Generator User's Manual.

from dataclasses import field
from typing import Union, Sequence, Optional
import rti.idl as idl
import rti.rpc as rpc
from enum import IntEnum
import sys
import os
from abc import ABC



CoSimTypes = idl.get_module("CoSimTypes")

@idl.struct(
    type_annotations = [idl.type_name("CoSimTypes::PingSM")])
class CoSimTypes_PingSM:
    I_demanda: float = 0.0
    V_SM: float = 0.0
    P_SM: float = 0.0
    I_SM: float = 0.0

CoSimTypes.PingSM = CoSimTypes_PingSM

@idl.struct(
    type_annotations = [idl.type_name("CoSimTypes::PongN2")])
class CoSimTypes_PongN2:
    I_demanda_eco2: float = 0.0
    I_demanda: float = 0.0

CoSimTypes.PongN2 = CoSimTypes_PongN2
