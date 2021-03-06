#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Nov 11 10:29:50 2020

@author: florianma
"""
import numpy as np
import os
import matplotlib.pyplot as plt
import pygmsh
import timeit
from tqdm import trange  # Progress bar
from dolfin import VectorElement, FiniteElement, Constant, inner, grad, div, \
    dx, Function, DirichletBC, Expression, solve, lhs, rhs, TestFunction, ds, \
    TrialFunction, dot, nabla_grad, split, errornorm, Mesh, plot, MeshEditor, \
    AutoSubDomain, MeshFunction, FacetNormal, assemble, Identity, \
    project, FunctionSpace, sym, Constant, TestFunctions, VectorFunctionSpace
from common import time_stepping, create2Dmesh, sigma, epsilon


# def setup_cylinder_problem(mesh, U0, coupled=True):
#     """
#     fenics code: build function space and define boundary conditions (bc).
#     """
#     return VQ, bcs, ds_


def navier_stokes_IPCS(mesh, dt, parameter):
    """
    fenics code: weak form of the problem.
    """
    mu, rho, nu = parameter
    V = VectorFunctionSpace(mesh, 'P', 2)
    Q = FunctionSpace(mesh, 'P', 1)

    bc0 = DirichletBC(V, Constant((0, 0)), cylinderwall)
    bc1 = DirichletBC(V, Constant((0, 0)), topandbottom)
    bc2 = DirichletBC(V, U0, inlet)
    bc3 = DirichletBC(Q, Constant(1), outlet)
    bcs = [bc0, bc1, bc2, bc3]

    # ds is needed to compute drag and lift. Not used here.
    ASD1 = AutoSubDomain(topandbottom)
    ASD2 = AutoSubDomain(cylinderwall)
    mf = MeshFunction("size_t", mesh, 1)
    mf.set_all(0)
    ASD1.mark(mf, 1)
    ASD2.mark(mf, 2)
    ds_ = ds(subdomain_data=mf, domain=mesh)

    vu, vp = TestFunction(V), TestFunction(Q)  # for integration
    u_, p_ = Function(V), Function(Q)  # for the solution
    u_1, p_1 = Function(V), Function(Q)  # for the prev. solution
    u, p = TrialFunction(V), TrialFunction(Q)  # unknown!
    bcu = [bcs[0], bcs[1], bcs[2]]
    bcp = [bcs[3]]

    n = FacetNormal(mesh)
    u_mid = (u + u_1) / 2.0
    F1 = rho*dot((u - u_1) / dt, vu)*dx \
        + rho*dot(dot(u_1, nabla_grad(u_1)), vu)*dx \
        + inner(sigma(u_mid, p_1, mu), epsilon(vu))*dx \
        + dot(p_1*n, vu)*ds - dot(mu*nabla_grad(u_mid)*n, vu)*ds
    a1 = lhs(F1)
    L1 = rhs(F1)
    # Define variational problem for step 2
    a2 = dot(nabla_grad(p), nabla_grad(vp))*dx
    L2 = dot(nabla_grad(p_1), nabla_grad(vp))*dx - (rho/dt)*div(u_)*vp*dx  # rho missing in FEniCS tutorial
    # Define variational problem for step 3
    a3 = dot(u, vu)*dx
    L3 = dot(u_, vu)*dx - dt*dot(nabla_grad(p_ - p_1), vu)*dx
    # Assemble matrices
    A1 = assemble(a1)
    A2 = assemble(a2)
    A3 = assemble(a3)
    # Apply boundary conditions to matrices
    [bc.apply(A1) for bc in bcu]
    [bc.apply(A2) for bc in bcp]
    return u_, p_, u_1, p_1, L1, A1, L2, A2, L3, A3, bcu, bcp


def solve_timestep(u_, p_, u_1, p_1, L1, A1, L2, A2, L3, A3, bcu, bcp):
    """
    fenics code: assemble matrices and solve system.
    """
    # Step 1: Tentative velocity step
    b1 = assemble(L1)
    [bc.apply(b1) for bc in bcu]
    solve(A1, u_.vector(), b1, 'bicgstab', 'hypre_amg')
    # Step 2: Pressure correction step
    b2 = assemble(L2)
    [bc.apply(b2) for bc in bcp]
    solve(A2, p_.vector(), b2, 'bicgstab', 'hypre_amg')
    # Step 3: Velocity correction step
    b3 = assemble(L3)
    solve(A3, u_.vector(), b3, 'cg', 'sor')
    # Update previous solution
    u_1.assign(u_)
    p_1.assign(p_)
    return u_1, p_1


def cylinder(lcar):
    with pygmsh.geo.Geometry() as geom:
        r = .05
        p = [geom.add_point([.20, .20], lcar),
             geom.add_point([0.0, .0], lcar),
             geom.add_point([2.2, .0], lcar),
             geom.add_point([2.2, .41], lcar),
             geom.add_point([0.0, .41], lcar),
             geom.add_point([.2+r, .20], lcar),
             geom.add_point([.20, .2+r], lcar),
             geom.add_point([.2-r, .20], lcar),
             geom.add_point([.20, .2-r], lcar)]
        c = [geom.add_line(p[1], p[2]),
             geom.add_line(p[2], p[3]),
             geom.add_line(p[3], p[4]),
             geom.add_line(p[4], p[1]),
             geom.add_circle_arc(p[5], p[0], p[6]),
             geom.add_circle_arc(p[6], p[0], p[7]),
             geom.add_circle_arc(p[7], p[0], p[8]),
             geom.add_circle_arc(p[8], p[0], p[5])]
        ll1 = geom.add_curve_loop([c[0], c[1], c[2], c[3]])
        ll2 = geom.add_curve_loop([c[4], c[5], c[6], c[7]])
        s = [geom.add_plane_surface(ll1, [ll2])]
        # s = [geom.add_plane_surface(ll1)]
        geom.add_surface_loop(s)
        msh = geom.generate_mesh()
    mesh = create2Dmesh(msh, 1)
    return mesh


def topandbottom(x, on_boundary):
    return (x[1] < 1e-6) or (.4099 < x[1]) and on_boundary


def cylinderwall(x, on_boundary):
    # bbx_x = (.1499 < x[0]) & (x[0] < .2501)
    # bbx_y = (.1499 < x[1]) & (x[1] < .2501)
    # return bbx_x and bbx_y and on_boundary
    in_circle = ((x[0]-.2)*(x[0]-.2) + (x[1]-.2)*(x[1]-.2)) < 0.0025001
    return (in_circle) & on_boundary


def inlet(x, on_boundary):
    return (x[0] < 1e-6) and on_boundary


def outlet(x, on_boundary):
    return (abs(x[0]-2.2) < 1e-6) and on_boundary


def plot_up(mesh, res):
    u, p = res[0], res[1]
    w0 = u.compute_vertex_values(mesh)
    w0.shape = (2, -1)
    magnitude = np.linalg.norm(w0, axis=0)
    x, y = np.split(mesh.coordinates(), 2, 1)
    u, v = np.split(w0, 2, 0)
    x, y, u, v = x.ravel(), y.ravel(), u.ravel(), v.ravel()
    tri = mesh.cells()
    pressure = p.compute_vertex_values(mesh)

    fig, (ax1, ax2) = plt.subplots(2, sharex=True, sharey=True,
                                   figsize=(12, 6))
    ax1.quiver(x, y, u, v, magnitude)
    ax2.tricontourf(x, y, tri, pressure, levels=40)
    ax1.set_aspect("equal")
    ax2.set_aspect("equal")
    ax1.set_title("velocity")
    ax2.set_title("pressure")
    return fig, (ax1, ax2)


if __name__ == "__main__":
    cfl = .05
    T = 8
    rho = 1.
    U_m = .3
    U_m = 1.5
    U0_str = "4.*U_m*x[1]*(.41-x[1])/(.41*.41)"
    mesh = cylinder(.02)
    U0 = Expression((U0_str, "0"), U_m=U_m, degree=2)
    x = [0, .41/2]  # evaluate the Expression at the center of the channel
    U_mean = 2/3*eval(U0_str)
    dt = cfl*mesh.hmin()/np.mean(U_mean)
    N = int((T/dt) // 1)
    L = .1

    # Re = 20.0
    for Re in [100, 20, 55, 65]: #, 20, 50, 60, 75, 100, 150, 200]:
        mu = rho*U_mean*L/Re
        nu = mu/rho
        parameter = [mu, rho, nu]
        my_dir = "../doc/mu({:.4f})/".format(mu)
        print(Re, my_dir)

        print(dt)
        print("Re set to: ", rho*U_mean*L/mu)
        print("Re set to: ", U_mean*L/nu)
        # print("Re set to: ", U_mean*.1/mu)
        print("cfl number: ", np.mean(U_mean)*dt/mesh.hmin())
        print(N, "timesteps")
        print("Unknowns: ", mesh.num_edges())
        print("coordinates: ", len(mesh.coordinates()))

        # VQ, bcs, ds_ = setup_cylinder_problem(mesh, U0, coupled=False)
        tic = timeit.default_timer()
        scheme = navier_stokes_IPCS
        solver = solve_timestep
        time_stepping(mesh, N, dt, parameter, scheme, solver, plot_up, my_dir)
        # time_stepping(mesh, VQ, bcs, ds_, N, dt, parameter,
        #               navier_stokes_IPCS, solve_timestep, plot_up, my_dir)
        toc = timeit.default_timer()

        print("time IPCS:", toc-tic)
        print("-----------------------end-of-iteration-----------------------")
