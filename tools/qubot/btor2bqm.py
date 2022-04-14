from typing import Dict

from dwave.system import DWaveSampler, EmbeddingComposite
from greedy import SteepestDescentComposite
from instructions import Instruction, State
from dimod import ExactSolver, SampleSet
from tools import *
from settings import *
import time
from qword_tools import InputPropagationFile, Solver
import json

class BTor2BQM:
    """
    interface to convert a btor2 file into a binary quadratic model
    """

    def __init__(self, n: int):
        '''

        :param n: number of instructions to execute
        '''
        self.n = n
        if n <= 0:
            raise Exception("number of instructions to execute cannot be less than 1.")

    def set_parameters(self, z3_solver_timeout, filename, output_path, initialize_states, modify_memory_sort, qpu_size):

        if z3_solver_timeout is not None:
            # set timeout (in milliseconds)
            print("setting custom z3_solver_timeout: ", z3_solver_timeout)
            Solver.timeout = z3_solver_timeout

        print("started building", filename, f"for {self.n} timesteps")
        Instruction.output_dir = output_path
        current_settings = get_btor2_settings(filename)
        print(current_settings)
        Instruction.set_setting(current_settings)
        InputPropagationFile.open_file(Instruction.output_dir)
        Instruction.initialize_states = initialize_states

        Instruction.clean_static_variables()

        Instruction.all_instructions = read_file(filename, modify_memory_sort=modify_memory_sort,
                                                 setting=current_settings)

        assert len(Instruction.all_instructions.keys()) > 0

        Instruction.QPU_SIZE = qpu_size

    def write_output_files(self, input_nid, total_time, time_to_fix):
        with open(f"{Instruction.output_dir}qubits_to_fix.json", "w") as outfile:
            json.dump(Instruction.qubits_to_fix, outfile)

        with open(f"{Instruction.output_dir}context.json", "w") as file:
            context = {
                "input": Instruction.created_states_ids[input_nid][1],
                "offset": Instruction.bqm.offset,
                "bad_states": Instruction.bad_states,
                "bad_states_to_line_no": Instruction.bad_states_to_line_no,
                "num_variables": len(Instruction.bqm.adj.keys()),
                "time_to_build": total_time,
                "time_to_fix": time_to_fix,
                "total_time": total_time + time_to_fix
            }
            json.dump(context, file)

        with open(f'{Instruction.output_dir}adj.coo', 'w') as file:
            for (v, neighbours) in Instruction.bqm.adj.items():
                file.write(f"{v} {v} {Instruction.bqm.linear[v]}\n")
                for (n, bias) in neighbours.items():
                    if v < n:
                        file.write(f"{v} {n} {bias}\n")

    def parse_file(self, filename: str, output_path: str, with_init=True, initialize_states=True, modify_memory_sort=True,
                   input_nid=81, z3_solver_timeout=None, QPU_SIZE=6000) -> dimod.BinaryQuadraticModel:

        self.set_parameters(z3_solver_timeout, filename, output_path, initialize_states, modify_memory_sort, QPU_SIZE)
        total_time = 0

        should_add_timestep = True
        i = 1
        while should_add_timestep:
            Instruction.current_n = i
            if i > self.n:
                break
            t0 = time.perf_counter()
            for instruction in Instruction.all_instructions.values():
                if instruction[1] == INIT and i == 1:
                    if with_init:
                        Instruction(instruction).execute()
                elif instruction[1] == NEXT:
                    Instruction(instruction).execute()
                elif instruction[1] == BAD:
                    Instruction(instruction).execute()

            # if error occur we should exit the loop, SMT-SOLVER finds the answer
            should_add_timestep = not Instruction.does_bad_state_occur(top_iter=self.n)
            tn = time.perf_counter()
            total_time += tn-t0
            i += 1

        # t0 = time.perf_counter()
        # Instruction.or_bad_states()
        # tn = time.perf_counter()
        # total_time += tn-t0

        t0_fix = time.perf_counter()
        Instruction.fix_qubits()
        tn_fix = time.perf_counter()
        time_to_fix = tn_fix - t0_fix
        InputPropagationFile.close_file()
        self.write_output_files(input_nid, total_time, time_to_fix)

        return Instruction.bqm

    @staticmethod
    def get_variable_value(line_number: int, timestep: int, result: SampleSet) -> None:
        if result is None:
            print("result is None.")
            return None
        qubits: Dict[str, int] = result[0]

        if line_number in Instruction.created_states_ids.keys():
            variable_names = Instruction.created_states_ids[line_number][timestep]
            binary_representation = []
            for name in variable_names:
                if name in Instruction.qubits_to_fix.keys():
                    binary_representation.append(Instruction.qubits_to_fix[name])
                else:
                    binary_representation.append(qubits[name])
            temp = [str(x) for x in binary_representation[::-1]]
            print(f"bin: {''.join(temp)}")
            print(f"decimal: {get_decimal_representation(binary_representation)}")

    @staticmethod
    def get_value_from_memory(offset: int, timestep: int, result: SampleSet) -> None:
        if Instruction.memory is None:
            print("No memory found")

        if timestep in Instruction.memory.keys():
            context_memory = Instruction.memory[timestep]
        else:
            context_memory = Instruction.memory.top

        local_offset = Instruction.address_to_local_offsets[offset]

        qubit_names = context_memory[local_offset*Instruction.WORD_SIZE : (local_offset*Instruction.WORD_SIZE + Instruction.WORD_SIZE)]

        qubits: Dict[str, int] = result[0]

        result = ""
        for name in qubit_names[::-1]:
            result += str(qubits[name])

        print(result)

    def run_exact_solver(self, filename: str,output_path, with_init=True, initialize_states=True, modify_memory_sort=True,
                         input_nid=81, qubit_growth_file=None) -> Optional[SampleSet]:
        print("parsing file")
        bqm = self.parse_file(filename, output_path, with_init=with_init, initialize_states=initialize_states, 
                              modify_memory_sort=modify_memory_sort, input_nid=input_nid, qubit_growth_file=qubit_growth_file)
        print("finished building BQM")
        if bqm.num_variables == 0:
            print("Empty binary quadratic model")
            return None
        if len(bqm.linear.keys()) > 21:
            print(f"Too many variables ({len(bqm.linear.keys())}). Cannot run exact solver.")
            return None
        sampler = ExactSolver()
        result = sampler.sample(bqm)
        print(f"result has energy: {round(result.first.energy, 2)}")
        return result

    def run_quantum_solver(self, filename: str, output_path, with_init=True, initialize_states=True, modify_memory_sort=True,
                   input_nid=81, qubit_growth_file=None, _num_reads=1000, chain_strength_=1):
        print("parsing file")
        bqm = self.parse_file(filename, output_path, with_init=with_init, initialize_states=initialize_states, 
                              modify_memory_sort=modify_memory_sort, input_nid=input_nid, qubit_growth_file=qubit_growth_file)
        print("finished building BQM")
        # qpu = DWaveSampler(solver={"name": "Advantage_system4.1"})
        # sampler = EmbeddingComposite(qpu)
        qpu = EmbeddingComposite(DWaveSampler(solver={"name": "Advantage_system4.1"}))
        sampler = SteepestDescentComposite(qpu)
        result = sampler.sample(bqm, num_reads=_num_reads, chain_strength=chain_strength_)
        print(f"lowest energy achieved: {round(result.first.energy, 2)}")
        return result
