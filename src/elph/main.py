from elph.workflow import run_j0, run_lambda, run_disp_j, run_matrix, run_tlt_mobility, run_svd_projection, submit_slurm_script
import elph.utils as ut
import argparse
import sys

def main():
    """ Main function to run el-ph coupling calculation
    """
    parser = argparse.ArgumentParser() # Create the parser
    parser.add_argument("-q", "--mesh", type=int, default=[8,8,8], nargs=3, help='Defining a mesh grid. (Defaults to [8,8,8]') # Add an argument: mesh
    parser.add_argument("-b", "--basis", type=str, default=['6-31G**','6-311G**'], nargs=2, help='Gaussian basis sets, first:local; second:non-local') # Add an argument: basis
    parser.add_argument("-f", "--functional", type=str, default=['b3lyp','b3lyp'], nargs=2, help='Gaussian functional, first:local; second:non-local') # Add an argument: functional
    parser.add_argument("-n", "--nmol", type=int, default=3, help='The number of molecules will be extracted') # Add an argument: nmol
    parser.add_argument("-s", "--supercell", type=int, nargs=3, default=(2,2,2), help='The supercell matrix (Defaults to (2,2,2) )') # Add an argument: supercell
    parser.add_argument("-o", "--output", type=str, default="tlt_mobility", help='Mobility calculation output name') # Add an argument: filename
    parser.add_argument("-svd", "--svdqpts", type=int, default=1, help='Number of qpoints that SVD projection will apply') # Add an argument: svd
    parser.add_argument("-w", "--workflow", type=int, default=1, help='Type in the workflow number to run corresponding simulation') # Add an argument: workflow
    parser.add_argument("-homo", "--homo", type=str, default=True, help='P-type: HOMO; N-type: LUMO') # Add an argument: homo
    parser.add_argument("-a", "--account", type=str, help="Submit VASP simulation on NERSC, type in your account!") # Add an argument: account
    parser.add_argument("-time", "--time", type=str, default="01:00:00", help="Submit VASP simulation on NERSC, type the time limit (format: hh:mm:ss)!") # Add an argument: time
    parser.add_argument("-l", "--local", action='store_true', default=False, help="VASP simulation running in local desktops!") # Add an argument: local
    parser.add_argument("-g", "--gpu", action='store_true', default=True, help="VASP 6 simulation running in HPC GPU nodes!") # Add an argument: gpu
    parser.add_argument("-H", "--hpc", type=int, nargs=3, default=[8,32,8], help="srun setting for VASP simulation, ex: srun -n {8} -c {32} -G {8} --cpu-bind=cores --gpu-bind=none vasp_std") # Add an argument: hpc

    args = parser.parse_args() # Parse the argument
    
    ut.print_start()

    # run locally 
    try:
        if not args.local:
            submit_slurm_script(args)
            return
        
        if args.workflow == 1: 
            run_j0(args.basis, args.functional, args.supercell, args.nmol) # Run Gaussian with optimization 

        elif args.workflow == 2: # Run workflow 2 (need to finish workflow 1 first)
            run_lambda(args.basis, args.functional)
            run_disp_j(args.basis, args.functional, args.nmol) # Create displaced dimers and calculate J_ij of dimers.
            run_matrix(args.mesh) # Calculate electron phonon coupling matrix (including local and non-local part)
        
        elif args.workflow == 3:  # Calculate the mobility
            run_tlt_mobility(output=args.output)                

        ut.print_end()

    except KeyboardInterrupt:
        ut.throw_error("Interrupted by user!")
