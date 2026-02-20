# -*- coding: utf-8 -*-

# -*- coding: utf-8 -*-
"""Workchain to compute the phonon dispersion from the raw initial unrelaxed structure."""
from aiida import orm
from aiida.common.extendeddicts import AttributeDict
from aiida.engine import ToContext, WorkChain, if_
from aiida.plugins import CalculationFactory, WorkflowFactory

PhBaseWorkChain = WorkflowFactory('quantumespresso.ph.base')
PwBaseWorkChain = WorkflowFactory('quantumespresso.pw.base')
Q2rBaseWorkChain = WorkflowFactory('quantumespresso.q2r.base')
MatdynBaseWorkChain = WorkflowFactory('quantumespresso.matdyn.base')

PhCalculation = CalculationFactory('quantumespresso.ph')


class PhInterpolateWorkChain(WorkChain):
    """Workchain to compute the interpolation steps for a phonon dispersion from the already computed Dyn mat."""

    @classmethod
    def define(cls, spec):
        """Define the work chain specification."""
        super().define(spec)
        spec.input(
            'dynmat_folder',
            valid_type=(orm.RemoteData, orm.FolderData),
            required=True,
            help='Retrieved folder containing the dynamical matrix'
        )
        spec.input(
            'dos',
            valid_type=orm.Bool,
            required=False,
            default=lambda: orm.Bool(True),
            help='Whether to compute the phonon density of states (DOS).',
        )
        spec.input(
            'kpoints_dispersion',
            valid_type=orm.KpointsData,
            required=True,
            help='Kpoints on which to compute phonon dispersion.',
        )
        spec.input(
            'kpoints_dos',
            valid_type=orm.KpointsData,
            required=False,
            help='Kpoints mesh for the phonon density of states (DOS).',
        )
        spec.expose_inputs(Q2rBaseWorkChain, namespace='q2r', exclude=('q2r.parent_folder',))
        spec.expose_inputs(
            MatdynBaseWorkChain,
            namespace='matdyn',
            exclude=('matdyn.force_constants', 'matdyn.kpoints'),
            namespace_options={'populate_defaults': False}
        )

        spec.outline(
            cls.setup,
            cls.run_q2r,
            cls.inspect_q2r,
            cls.run_matdyn,
            if_(cls.should_run_dos)(cls.run_matdyn_dos,),
            cls.results,
        )
        spec.output('output_parameters', valid_type=orm.Dict)
        spec.output('output_phonon_bands', valid_type=orm.BandsData)
        spec.output('output_phonon_dos', valid_type=orm.XyData, required=False)

        spec.exit_code(401, 'ERROR_Q2R_FAILED', message='The Q2rBaseWorkChain sub-workchain failed.')
        spec.exit_code(
            402, 'ERROR_MATDYN_FAILED', message='The MatdynBaseWorkChain sub-workchain for dispersion failed.'
        )
        spec.exit_code(403, 'ERROR_MATDYN_DOS_FAILED', message='The MatdynBaseWorkChain sub-workchain for DOS failed.')

    def setup(self):
        """Initialize context variables."""
        #self.ctx.structure = self.inputs.pw.pw.structure

    def run_q2r(self):
        """Run the Q2rCalculation."""
        inputs = AttributeDict(self.inputs.q2r)

        # Load parent folder from completed PhBaseWorkChain if not provided in inputs
        #if 'parent_folder' not in inputs:
        inputs['q2r']['parent_folder'] = self.inputs.dynmat_folder

        running = self.submit(Q2rBaseWorkChain, **inputs)

        self.report(f'launching Q2rBaseWorkChain<{running.pk}>')

        return ToContext(workflow_q2r=running)

    def inspect_q2r(self):
        """Inspect the Q2rCalculation result."""
        if not self.ctx.workflow_q2r.is_finished_ok:
            return self.exit_codes.ERROR_Q2R_FAILED

        self.ctx.force_constants = self.ctx.workflow_q2r.outputs.force_constants

    def run_matdyn(self):
        """Run the MatdynCalculation."""
        inputs = AttributeDict(self.inputs.matdyn)

        inputs['matdyn']['force_constants'] = self.ctx.force_constants
        inputs['matdyn']['kpoints'] = self.inputs.kpoints_dispersion

        parameters = inputs['matdyn'].get('parameters', orm.Dict({})).get_dict()
        parameters['INPUT']['dos'] = False
        inputs['matdyn']['parameters'] = orm.Dict(parameters)

        running = self.submit(MatdynBaseWorkChain, **inputs)

        self.report(f'launching MatdynBaseWorkChain<{running.pk}>')

        return ToContext(workflow_matdyn=running)

    def should_run_dos(self):
        """Determine whether to run the MatdynCalculation for DOS."""
        return self.inputs.dos.value

    def run_matdyn_dos(self):
        """Run the MatdynCalculation."""
        inputs = AttributeDict(self.inputs.matdyn)

        inputs['matdyn']['force_constants'] = self.ctx.force_constants
        inputs['matdyn']['kpoints'] = self.inputs.kpoints_dos

        parameters = inputs['matdyn'].get('parameters', orm.Dict({})).get_dict()
        parameters['INPUT']['dos'] = True
        inputs['matdyn']['parameters'] = orm.Dict(parameters)

        running = self.submit(MatdynBaseWorkChain, **inputs)

        self.report(f'launching MatdynBaseWorkChain<{running.pk}>')

        return ToContext(workflow_matdyn_dos=running)

    def results(self):
        """Run the final step after computing the dispersion steps."""
        matdyn_calc = self.ctx.workflow_matdyn
        matdyn_dos = self.ctx.get('workflow_matdyn_dos', None)

        if not matdyn_calc.is_finished_ok:
            return self.exit_codes.ERROR_MATDYN_FAILED

        if matdyn_dos is not None and not matdyn_dos.is_finished_ok:
            return self.exit_codes.ERROR_MATDYN_DOS_FAILED

        self.out('output_parameters', matdyn_calc.outputs.output_parameters)
        self.out('output_phonon_bands', matdyn_calc.outputs.output_phonon_bands)
        if matdyn_dos is not None:
            self.out('output_phonon_dos', matdyn_dos.outputs.output_phonon_dos)
