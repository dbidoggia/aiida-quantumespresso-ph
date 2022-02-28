# -*- coding: utf-8 -*-
"""Workchain to compute the phonon dispersion from the raw initial unrelaxed structure."""
from aiida import orm
from aiida.common.extendeddicts import AttributeDict
from aiida.plugins import WorkflowFactory, CalculationFactory
from aiida.tools.data.array.kpoints import get_explicit_kpoints_path
from aiida.engine import calcfunction, WorkChain, ToContext, if_

PhBaseWorkChain = WorkflowFactory('quantumespresso.ph.base')
#PhBaseWorkChain = WorkflowFactory('kotiuga_phonon.ph.base')
PwBaseWorkChain = WorkflowFactory('quantumespresso.pw.base')
Q2rBaseWorkChain = WorkflowFactory('quantumespresso.q2r.base')
MatdynBaseWorkChain = WorkflowFactory('quantumespresso.matdyn.base')

PhCalculation = CalculationFactory('quantumespresso.ph')


class DynamicalMatrixWorkChain(WorkChain):
    """Workchain to compute the dynamical matrix from a structure (no relaxation)."""

    @classmethod
    def define(cls, spec):
        # yapf: disable
        super().define(spec)
        spec.expose_inputs(PwBaseWorkChain, namespace='pwWC')

        spec.expose_inputs(PhBaseWorkChain, namespace='phWC', exclude=('ph.parent_folder',))
        spec.input('ph_parent', valid_type=orm.RemoteData, required=False, help='Ph parent if already ran ...hi')
        spec.outline(
            cls.setup,
            cls.run_pw,
            cls.run_ph,
            cls.results,
        )

        spec.output('pw_output_parameters', valid_type=orm.Dict)
        spec.output('ph_output_parameters', valid_type=orm.Dict)
        spec.output('ph_retrieved', valid_type=orm.FolderData)
        




    def setup(self):
        """Initialize context variables."""
        if 'ph_parent' in self.inputs: 
            self.ctx.ph_parent = self.inputs.ph_parent
        else:
            self.report('no parent given')


    def run_pw(self):
        """Run the PwBaseWorkChain."""
        inputs = AttributeDict(self.inputs.pwWC)

        running = self.submit(PwBaseWorkChain, **inputs)

        self.report('launching PwBaseWorkChain<{}>'.format(running.pk))

        return ToContext(workflow_pw=running)

    def run_ph(self):
        """Run the PhWorkChain."""
        inputs = AttributeDict(self.inputs.phWC)

        if 'ph_parent' in self.ctx: 
            inputs['ph']['parent_folder'] = self.inputs.ph_parent
            self.report('PH calculation with parent folder from user')
        else:
            inputs['ph']['parent_folder'] = self.ctx.workflow_pw.outputs.remote_folder
            self.report('PH calculation with parent folder from PW run')

        running = self.submit(PhBaseWorkChain, **inputs)

        self.report('launching PhBaseWorkChain<{}>'.format(running.pk))

        return ToContext(workflow_ph=running)


    def results(self):
        """Attach the desired output nodes directly as outputs of the workchain."""
        self.report('workchain succesfully completed')
        self.out('pw_output_parameters', self.ctx.workflow_pw.outputs.output_parameters)
        self.out('ph_output_parameters', self.ctx.workflow_ph.outputs.merged_output_parameters) # change name ph_merged_out & add last ph
        self.out('ph_retrieved', self.ctx.workflow_ph.outputs.retrieved)
