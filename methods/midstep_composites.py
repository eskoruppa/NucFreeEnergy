import sys, os
import numpy as np
from typing import List, Tuple, Callable, Any, Dict

from .PolyCG.polycg.SO3 import so3
from .PolyCG.polycg.transforms.transform_SO3 import euler2rotmat_so3
from .PolyCG.polycg.transforms.transform_marginals import send_to_back_permutation

    
def midstep_se3_groundstate(groundstate: np.ndarray):
    Phi0s = groundstate[:,:3]
    N = len(groundstate)
    # assign static rotation matrices
    srots = np.zeros((N,3,3))
    srots[0]  = so3.euler2rotmat(0.5*Phi0s[0])    
    srots[-1] = so3.euler2rotmat(0.5*Phi0s[-1])    
    for l in range(1,len(srots)-1):
        srots[l] = so3.euler2rotmat(Phi0s[l])   
    # assign translation vectors
    trans = np.copy(groundstate[:,3:])
    trans[0] = 0.5*trans[0]
    trans[-1] = 0.5* srots[-1].T @ trans[-1]
    
    Smats = np.zeros((N,4,4))
    for i in range(N):
        S = np.zeros((4,4))
        S[:3,:3] = srots[i]
        S[:3,3]  = trans[i]
        S[3,3]   = 1
        Smats[i] = S
    return Smats



def midstep_composition_transformation(
    groundstate: np.ndarray,
    midstep_constraint_locations: List[int],
) -> np.ndarray:
    N = len(groundstate)
    mat = np.eye(N*6)
    replaced_ids = []
    for i in range(len(midstep_constraint_locations)-1):
        id1 = midstep_constraint_locations[i]
        id2 = midstep_constraint_locations[i+1]
        replace_id = id2
        partial_gs = groundstate[id1:id2+1]
        midstep_comp_block = midstep_composition_block(partial_gs)
        mat[replace_id*6:replace_id*6+6,id1*6:id2*6+6] = midstep_comp_block
        replaced_ids.append(replace_id)
    return mat, replaced_ids

def midstep_composition_block(
    groundstate: np.ndarray
) -> np.ndarray:
    if len(groundstate) < 2:
        raise ValueError(f'midstep_composition_block: grounstate needs to contain at least two elements. {len(groundstate)} provided.')
    
    Phi0s = groundstate[:,:3]
    # ss    = groundstate[:,3:]
    
    N = len(groundstate)
    # assign static rotation matrices
    srots = np.zeros((N,3,3))
    srots[0]  = so3.euler2rotmat(0.5*Phi0s[0])    
    srots[-1] = so3.euler2rotmat(0.5*Phi0s[-1])    
    for l in range(1,len(srots)-1):
        srots[l] = so3.euler2rotmat(Phi0s[l])    
    
    # assign translation vectors
    trans = np.copy(groundstate[:,3:])
    trans[0] = 0.5*trans[0]
    trans[-1] = 0.5* srots[-1].T @ trans[-1]
    
    ndims = 6
    N = len(groundstate)
    i = 0
    j = N-1
    comp_block  = np.zeros((ndims,N*ndims))
    
    ################################  
    # set middle blocks (i < k < j)
    for k in range(i,j+1):
        Saccu = midstep_Saccu(srots,k+1,j)
        comp_block[:3,k*6:k*6+3]   = Saccu.T
        comp_block[3:,k*6+3:k*6+6] = Saccu.T
        
        coup = np.zeros((3,3))
        for l in range(k+1,j+1):
            coup += so3.hat_map(-midstep_Saccu(srots,l,j).T @ trans[l])
        coup = coup @ Saccu.T
        comp_block[3:,k*6:k*6+3] = coup
    
    ################################  
    # set first block (i)
    Saccu = midstep_Saccu(srots,i+1,j)
    Phi_0 = Phi0s[0]
    H_half = so3.splittransform_algebra2group(0.5*Phi_0)
    Hinv   = so3.splittransform_group2algebra(Phi_0)
    Hprod  = H_half @ Hinv
    
    # assign diagonal blocks
    comp_block[:3,:3] = 0.5 * Saccu.T @ Hprod
    comp_block[3:,3:6] = 0.5 * Saccu.T
    
    coup = np.zeros((3,3))
    # first term
    for l in range(1,j+1):
        coup += so3.hat_map(-midstep_Saccu(srots,l,j).T @ trans[l])
    coup = coup @ Saccu.T
    # second term
    coup += Saccu.T @ srots[i].T @ so3.hat_map(trans[i])
    # multiply everything with 0.5 * Hprod
    coup = 0.5 * coup @ Hprod
    # assign coupling term
    comp_block[3:,:3] = coup
    
    ################################  
    # set last block (j)
    Phi_0 = Phi0s[-1]
    H_half = so3.splittransform_algebra2group(0.5*Phi_0)
    Hinv   = so3.splittransform_group2algebra(Phi_0)
    Hprod  = H_half @ Hinv
    
    # assign diagonal blocks
    comp_block[:3,j*6:j*6+3]   = 0.5 * Hprod
    comp_block[3:,j*6+3:j*6+6] = 0.5 * srots[-1]
        
    return comp_block


def midstep_composition_transformation_correction(
    groundstate: np.ndarray,
    midstep_constraint_locations: List[int],
    correction: np.ndarray
) -> np.ndarray:
    N = len(groundstate)
    mat = np.eye(N*6)
    replaced_ids = []
    for i in range(len(midstep_constraint_locations)-1):
        id1 = midstep_constraint_locations[i]
        id2 = midstep_constraint_locations[i+1]
        replace_id = id2
        partial_gs = groundstate[id1:id2+1]
        partial_correction = correction[id1:id2+1]
        midstep_comp_block = midstep_composition_block_correction(partial_gs,partial_correction)
        mat[replace_id*6:replace_id*6+6,id1*6:id2*6+6] = midstep_comp_block
        replaced_ids.append(replace_id)
    return mat, replaced_ids


def midstep_composition_block_correction(
    groundstate: np.ndarray,
    deformations: np.ndarray
) -> np.ndarray:
    if len(groundstate) < 2:
        raise ValueError(f'midstep_composition_block: grounstate needs to contain at least two elements. {len(groundstate)} provided.')
    
    Phi0s = groundstate[:,:3]
    # ss    = groundstate[:,3:]
    Phids = deformations[:,:3]
    
    N = len(groundstate)
    # assign static rotation matrices
    srots = np.zeros((N,3,3))
    srots[0]  = so3.euler2rotmat(0.5*Phi0s[0])    
    srots[-1] = so3.euler2rotmat(0.5*Phi0s[-1])    
    for l in range(1,len(srots)-1):
        srots[l] = so3.euler2rotmat(Phi0s[l])
        
    drots = np.zeros((N,3,3))
    
    Phi_0 = Phi0s[0]
    H_half = so3.splittransform_algebra2group(0.5*Phi_0)
    Hinv   = so3.splittransform_group2algebra(Phi_0)
    Hprod  = H_half @ Hinv
    drots[0]  = so3.euler2rotmat(0.5*Hprod @ Phids[0]) 
    
    Phi_0 = Phi0s[-1]
    H_half = so3.splittransform_algebra2group(0.5*Phi_0)
    Hinv   = so3.splittransform_group2algebra(Phi_0)
    Hprod  = H_half @ Hinv
    drots[-1]  = so3.euler2rotmat(0.5*Hprod @ Phids[-1]) 
    
    # drots[0]  = so3.euler2rotmat(0.5*Phids[0])    
    # drots[-1] = so3.euler2rotmat(0.5*Phids[-1])    
    for l in range(1,len(drots)-1):
        drots[l] = so3.euler2rotmat(Phids[l])
        
    rrots = np.zeros((N,3,3))
    for l in range(len(drots)):
        rrots[l] = srots[l] @ drots[l]
    
    # assign translation vectors
    trans = np.copy(groundstate[:,3:])
    trans[0] = 0.5*trans[0]
    trans[-1] = 0.5* srots[-1].T @ trans[-1]
    
    ndims = 6
    N = len(groundstate)
    i = 0
    j = N-1
    comp_block  = np.zeros((ndims,N*ndims))
    
    ################################  
    # set middle blocks (i < k < j)
    for k in range(i,j+1):
        Saccu = midstep_Saccu(srots,k+1,j)
        Raccu = midstep_Saccu(rrots,k+1,j)
        comp_block[:3,k*6:k*6+3]   = Saccu.T
        comp_block[3:,k*6+3:k*6+6] = Raccu.T
        
        coup = np.zeros((3,3))
        for l in range(k+1,j+1):
        #     coup += so3.hat_map(-midstep_Saccu(srots,l,j).T @ trans[l])
        # coup = coup @ Saccu.T
            coup += so3.hat_map(-midstep_Saccu(rrots,l,j).T @ trans[l])
        coup = coup @ Raccu.T
        comp_block[3:,k*6:k*6+3] = coup
    
    ################################  
    # set first block (i)
    Saccu = midstep_Saccu(srots,i+1,j)
    Raccu = midstep_Saccu(rrots,i+1,j)
    Phi_0 = Phi0s[0]
    H_half = so3.splittransform_algebra2group(0.5*Phi_0)
    Hinv   = so3.splittransform_group2algebra(Phi_0)
    Hprod  = H_half @ Hinv
    
    # assign diagonal blocks
    comp_block[:3,:3] = 0.5 * Saccu.T @ Hprod
    comp_block[3:,3:6] = 0.5 * Raccu.T
    
    coup = np.zeros((3,3))
    # first term
    for l in range(1,j+1):
        coup += so3.hat_map(-midstep_Saccu(rrots,l,j).T @ trans[l])
    coup = coup @ Raccu.T
    # second term
    coup += Saccu.T @ srots[i].T @ so3.hat_map(trans[i])
    # multiply everything with 0.5 * Hprod
    coup = 0.5 * coup @ Hprod
    # assign coupling term
    comp_block[3:,:3] = coup
    
    ################################  
    # set last block (j)
    Phi_0 = Phi0s[-1]
    H_half = so3.splittransform_algebra2group(0.5*Phi_0)
    Hinv   = so3.splittransform_group2algebra(Phi_0)
    Hprod  = H_half @ Hinv
    
    # assign diagonal blocks
    comp_block[:3,j*6:j*6+3]   = 0.5 * Hprod
    comp_block[3:,j*6+3:j*6+6] = 0.5 * rrots[-1]
        
    return comp_block


def midstep_Saccu(srots: np.ndarray,i,j) -> np.ndarray:
    saccu = np.eye(3)
    for k in range(i,j+1):
        saccu = saccu @ srots[k]
    return saccu


# def midstep_srots_and_trans(groundstate: np.ndarray) -> np.ndarray:
#     Phi0s = groundstate[:,:3]
#     N = len(Phi0s)
#     srots = np.zeros((N,3,3))
#     srots[0]  = so3.euler2rotmat(0.5*Phi0s[0])    
#     srots[-1] = so3.euler2rotmat(0.5*Phi0s[-1])    
#     for l in range(1,len(srots)-1):
#         srots[l] = so3.euler2rotmat(Phi0s[l])  
    
#     trans = np.copy(groundstate[:,3:])
#     trans[0] = 0.5*trans[0]
#     trans[-1] = 0.5* srots[-1].T @ trans[-1]
#     return srots, trans

