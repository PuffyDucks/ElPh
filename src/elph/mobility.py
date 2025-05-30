# Charge carrier mobility using Transient Localization Theory (TLT)
import numpy as np
import sys
import json
import elph.utils as ut
from scipy.constants import e, hbar, k

jtoev = 6.241509074460763e+18 # Convert J to eV

class Mobility():
    """
    Args:
    atoms (np.array): containing the positions of the atoms in the crystal unit cell as rows, expressed in units of the lattice parameter. 
    nx (int): indicating the number of times the crystal unit cell is repeated along the x coordinate axis. 
    ny (int): indicating the number of times the crystal unit cell is repeated along the y coordinate axis. 
    nz (int): indicating the number of times the crystal unit cell is repeated along the z coordinate axis.
    lattice_vecs (np.array): Unit cell lattice vectors
    plane (list): The 2D plane for charge transport (ex: yz plane is [1,2])
    distances (list): Specific interaction distances to consider
    translation_dist (float): One of the lattice parameter will be consider into interaction
    j_ii (float): Intra-molecular transfer integral (Onsite energy) (ex: J_ii)
    j_ij (list): Inter-molecular transfer integral (ex: J_a, J_b, J_c)
    sigma_ii (float): local electronic phonon coupling (ex: sigma_ii)
    sigma_ij (list): nonlocal electronic phonon coupling (dynamic disorder) (ex: sigma_a, sigma_b, sigma_c)
    temp (float): Temperature in Kelvin (Defaults to 300)
    inverse_htau (float): Inverse of the scattering time (hbar/tau) units in eV (Defaults to 5e-3)
    is_hole (bool): If True, hole transport, otherwise electron transport (Defaults to True)
    realizations (int): Number of realizations for average calculation (Defaults to 250)
    mob_file (str): The json file containing the mobility parameters (Defaults to "mobility.json")
    """
    def __init__(self, atoms=None, nx=1, ny=1, nz=1, lattice_vecs=None, plane=None, distances=None, translation_dist=None, j_ii=0.0, j_ij=None, sigma_ii=0.0, sigma_ij=None, temp=300.0, inverse_htau=5e-3, is_hole=True,realizations=250, 
                 mob_file="mobility.json"):
        
        if mob_file:
            with open(mob_file, "r") as file:
                config = json.load(file)
            
            self.atoms = np.array(config.get("atoms", atoms))
            self.nx = config.get("nx", nx)
            self.ny = config.get("ny", ny)
            self.nz = config.get("nz", nz)
            self.lattice_vecs = np.array(config.get("lattice_vecs", lattice_vecs))
            self.plane = config.get("plane", plane)
            self.distances = config.get("distances", distances)
            self.translation_dist = config.get("translation_dist", translation_dist)
            self.j_ii = config.get("j_ii", j_ii)
            self.j_ij = config.get("j_ij", j_ij)
            self.sigma_ii = config.get("sigma_ii", sigma_ii)
            self.sigma_ij = config.get("sigma_ij", sigma_ij)
            self.temp = config.get("temp", temp)
            self.inverse_htau = config.get("inverse_htau", inverse_htau)
            self.is_hole = config.get("is_hole", is_hole)
            self.realizations = config.get("realizations", realizations)
        
        else:
            ut.print_error("Mobility parameters (mobility.json) are missing!")
            sys.exit(0)

    def generate_lattice(self):
        '''
        This function generates a lattice of atoms to populate a simulation cell.
        Returns:
        positions (np.array): containing the positions of the atoms in the
        simulation cell as rows, expressed in units of the lattice parameter.
        '''
        n_in_cell = self.atoms.shape[0]
        positions = np.zeros((n_in_cell * self.nx * self.ny * self.nz, 3))
    
        count = 0
        for a in range(self.nx):
            for b in range(self.ny):
                for c in range(self.nz):
                    positions[count:(count + n_in_cell),] = self.atoms + [a, b, c]
                    count += n_in_cell
        return positions

    def dist_pbc(self, dist_vecs):
        """ Apply minimum image convention (PBC) on distance vectors
        Args:
        dist_vecs (np.array): The distance vectors array
        -----------------------------------------------
        Return:
        dist_vecs (np.array): The distance vectors array after applying PBC
        """
        for i in range(3):  # 3D case: x, y and z
            if dist_vecs[:, :, i].any() > self.lattice_vecs[i, i] / 2.:
                dist_vecs[:, :, i] -= self.lattice_vecs[i, i]
            elif dist_vecs[:, :, i].any() < -self.lattice_vecs[i, i] / 2.:
                dist_vecs[:, :, i] += self.lattice_vecs[i, i]
     
        return dist_vecs

    def interactions(self):
        """
        Compute pairwise interactions with periodic boundary conditions.
        args:
        postions (np.array): The positions of the atoms in the simulation cell
        lattice_vectors (np.array (2x2)): Unit cell lattice vectors
        plane (list): The 2D plane for charge transport (ex: yz plane is [1,2]
        distances (list): Specific interaction distances to consider
        translation_dist (float): One of the lattice parameter will be consider into interaction
        --------------------------------------------------------------------
        Returns:
        interaction_matrix (np.array): The interaction matrix
        dist_vecs (np.array): The distance vectors array
        """
        positions = self.generate_lattice() # Generate lattice
        lattice = np.dot(positions, self.lattice_vecs.T) # supercell lattice points
    
        N = len(lattice) # number of molecules in supercell
    
        dist_vecs = lattice[:, None, :] - lattice[None, :, :] # Compute all pairwise distance vectors (dist_vecs.shape = (N,N,3))
        dist_vecs = self.dist_pbc(dist_vecs) # apply PBC 
    
        distances = np.linalg.norm(dist_vecs, axis=-1) # Compute Euclidean distance matrix

        interaction_matrix = np.zeros((N, N), dtype=int)
        for idx, d in enumerate(self.distances, start=1):
            interaction_matrix[np.isclose(distances, d, atol=1e-4)] = idx  # Assign type 1, 2, 3

        for i in range(N):
            for j in range(N):
                if np.any(np.isclose(np.linalg.norm(lattice[i] - lattice[j]), self.translation_dist, atol=1e-4)): # Modify interactions where distance = lattice vector to a specific type (e.g., type 3)
                    interaction_matrix[i, j] = 3

        # ======= Apply Group Mask to Type 1 Interactions =======
        type1_mask = interaction_matrix == 1  # Find type 1 interactions
    
        # Get sign of displacement vectors
        signs = np.sign(dist_vecs)
 
        #   (       *      *     *        ")
        #   (                             ")
        #   (   #      2#      3#         ")
        #   (                             ")
        #   (       *      1*    *        ")
        #   (                             ")
        #   (   #      #       #          ")

        # 1 -> 2: interaction type 1 (Distance are equal but direction are opposite)
        # 1 -> 3: interaction type 2
        # 2 -> 3: interaction type 3

        # Define masks
        group1_mask = (signs[..., self.plane[0]] != signs[..., self.plane[1]])  # Opposite sign: (+,-) or (-,+)
        group2_mask = (signs[..., self.plane[0]] == signs[..., self.plane[1]])  # Same sign: (+,+) or (-,-)

        # Apply masks only to type 1 interactions
        interaction_matrix[type1_mask & group1_mask] = 1  # Keep type 1
        interaction_matrix[type1_mask & group2_mask] = 2  # Reassign to type 2

        return dist_vecs, interaction_matrix

    def hamiltonian(self):
        """ Define the tight-binding Hamiltonian matrix for the charge carrier.
        H = H_el + H_ph + H_elph
        in original TLT: H_ph = 0, H_ii = 0; but we can add H_ii and H_elph,l
        H = (H_ii + H_elph,l) + H_ij + H_elph,nl
        ---------------------------------------------
        Return:
        H: Hamiltonian matrix
        """
        _, interaction_matrix = self.interactions()
        Hij_matrix = np.copy(interaction_matrix).astype(float) # Transfer integral matrix (J_ij)
        sigmaij_matrix = np.copy(interaction_matrix).astype(float) # Dynamic disorder matrix (in TLT, we treat this as static disorder)

        # Onsite energy matrix (H_ii)
        Hii_matrix = np.diag([self.j_ii]*interaction_matrix.shape[0])
        sigmaii_matrix = np.diag([self.sigma_ii]*interaction_matrix.shape[0]) # Dynamic disorder matrix (in TLT, we treat this as static disorder)

        # Inter-molecular transfer integral matrix (H_ij)
        j1 = self.j_ij[0]
        j2 = self.j_ij[1]
        j3 = self.j_ij[2]

        Hij_matrix[Hij_matrix==1] = j1
        Hij_matrix[Hij_matrix==2] = j2
        Hij_matrix[Hij_matrix==3] = j3

        s1 = self.sigma_ij[0]
        s2 = self.sigma_ij[1]
        s3 = self.sigma_ij[2]

        sigmaij_matrix[sigmaij_matrix==1] = s1
        sigmaij_matrix[sigmaij_matrix==2] = s2
        sigmaij_matrix[sigmaij_matrix==3] = s3

        #np.random.seed(42)  # Ensures same random values each time
        gaussian_matrix = np.random.normal(0, 1, size=interaction_matrix.shape)
        gaussian_matrix = np.tril(gaussian_matrix) + np.tril(gaussian_matrix, -1).T
    
        H = Hii_matrix + Hij_matrix + sigmaij_matrix * gaussian_matrix

        return H

    def localization(self):
        """
        Calculate the localization length of the charge carrier.
        Args:
        dist_vecs (np.array): The distance vectors array from interactions()
        interaction_matrix (np.array): The interaction matrix from interactions()
        inverse_htau (float): Inverse of the scattering time (hbar/tau) units in eV
        h_ij (np.array): The Hamiltonian matrix from hamiltonian()
        -----------------------------------------------------------------
        Return:
        lx2 (float): The localization length in x direction
        ly2 (float): The localization length in y direction
        """
        positions = self.generate_lattice()
        factor = -1
        if not self.is_hole: # If hole transport, it will transport at the top edge of the valence band, Boltzmann factor will be positive
            factor = 1

        beta = 1 / (k * jtoev * self.temp) # Boltzmann factor 
        h_ij = self.hamiltonian() # Create Hamiltonian matrix
        energies, eigenvecs = np.linalg.eigh(h_ij) # Solve eigenvalues & eigenvectors
        operx = np.diag(positions[:,self.plane[0]])
        opery = np.diag(positions[:,self.plane[1]])
        weights = np.exp(-factor * energies * beta)
        partition = np.sum(weights)
    
        mxX = (eigenvecs.conj().T @ operx @ eigenvecs) # <n|x|m>, where x is the position operator
        mxY = (eigenvecs.conj().T @ opery @ eigenvecs)

        eng_diff = energies[:, None] - energies[None, :]
        mxX *= eng_diff # (En-Em) * <n|x|m>
        mxY *= eng_diff

        lx2 = sum(sum(weights * (np.abs(mxX)**2) * 2 / (self.inverse_htau**2 + eng_diff**2)))
        ly2 = sum(sum(weights * (np.abs(mxY)**2) * 2 / (self.inverse_htau**2 + eng_diff**2)))

        lx2 /= partition
        ly2 /= partition
        
        #operatorx = np.matmul(eigenvecs.T, np.matmul(dist_vecs[:,:,self.plane[0]] * h_ij, eigenvecs))
        #operatorx -= np.matmul(eigenvecs.T, np.matmul(dist_vecs[:,:,self.plane[0]] * h_ij, eigenvecs)).T

        #operatory = np.matmul(eigenvecs.T, np.matmul( dist_vecs[:,:,self.plane[1]]* h_ij, eigenvecs))
        #operatory -= np.matmul(eigenvecs.T, np.matmul(dist_vecs[:,:,self.plane[1]] * h_ij, eigenvecs)).T

        return lx2, ly2

    def avg_localization(self):
        """ 
        Perform average of the localization length calculation.
        Args:
        positions (np.array): The positions of the atoms in the simulation cell
        lattice_vectors (np.array): Unit cell lattice vectors
        distances (list): Specific interaction distances to consider
        j_ij (list): Inter-molecular transfer integral (J_a, J_b, J_c)
        sigma (list): dynamic disorder (sigma_a, sigma_b, sigma_c)
        translation_dist (float): One of the lattice parameter will be consider into interaction
        inverse_htau (float): Inverse of the scattering time (hbar/tau) units in eV (Defaults to 5e-3)
        temp (float): Temperature in Kelvin (Defaults to 300)
        -----------------------------------------------------------------
        Return:
        avg_lx2 (float): The average square localization length in x direction
        avg_ly2 (float): The average square localization length in y direction
        """
        avglx2_list = []
        avgly2_list = []
        for n in range(self.realizations):
            lx2, ly2 = self.localization() # Calculation lx^2 and ly^2 
            avglx2_list.append(lx2)
            avgly2_list.append(ly2)

        avglx2 = sum(avglx2_list) / self.realizations
        avgly2 = sum(avgly2_list) / self.realizations
    
        return avglx2, avgly2

    def tlt_mobility(self):
        """
        TLT mobility calculation.
        Args:
        avg_lx2 (float): The average localization length in x direction
        avg_ly2 (float): The average localization length in y direction
        inverse_htau (float): Inverse of the scattering time (hbar/tau) units in eV
        temp (float): Temperature in Kelvin
        ---------------------------------------------------------------
        Return:
        mobilityx
        mobilityy
        mobility_average
        """
        avglx2, avgly2 = self.avg_localization()
        tau = hbar * jtoev / self.inverse_htau # unit: second
        mobilityx = 1e-16 * e * avglx2 / (2 * tau * k * self.temp) # Unit is cm^2/Vs
        mobilityy = 1e-16 * e * avgly2 / (2 * tau * k * self.temp)
        mobility_average = 1e-16 * e * 0.5 * (avglx2 + avgly2) / (2 * tau * k * self.temp)

        return avglx2, avgly2, mobilityx, mobilityy, mobility_average

