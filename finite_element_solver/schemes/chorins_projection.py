#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Mar  4 11:30:48 2021

@author: florianma

Simulation gets slower and slower. 1st iteration takes 2s, 10th iteration 30s.
"""
from dolfin import (inner, grad, div, dx, solve, lhs, rhs, ds, dot, nabla_grad,
                    FacetNormal, assemble, outer, Constant, Identity, sym)


def epsilon(u):
    # Define symmetric gradient
    return sym(nabla_grad(u))


def sigma(u, p, mu):
    # Define stress tensor
    return 2 * mu * epsilon(u) - p * Identity(len(u))


class TutorialTentativeVelocityStep():
    def __init__(self, domain):
        rho, mu, dt = domain.rho, domain.mu, domain.dt
        u, u_1, vu = domain.u, domain.u_1, domain.vu
        p_1 = domain.p_1

        n = FacetNormal(domain.mesh)
        u_mid = (u + u_1) / 2.0
        F1 = rho * dot((u - u_1) / dt, vu) * dx \
            + rho * dot(dot(u_1, nabla_grad(u_1)), vu) * dx \
            + inner(sigma(u_mid, p_1, mu), epsilon(vu)) * dx \
            + dot(p_1 * n, vu) * ds - dot(mu * nabla_grad(u_mid) * n, vu) * ds
        a1 = lhs(F1)
        L1 = rhs(F1)
        A1 = assemble(a1)
        [bc.apply(A1) for bc in domain.bcu]

        self.a1, self.L1, self.A1 = a1, L1, A1
        self.domain = domain
        return

    def solve(self):
        bcu, u_ = self.domain.bcu, self.domain.u_
        A1, L1 = self.A1, self.L1

        b1 = assemble(L1)
        [bc.apply(b1) for bc in bcu]
        solve(A1, u_.vector(), b1, 'bicgstab', 'hypre_amg')
        return


class ImplicitTentativeVelocityStep():
    def __init__(self, domain):
        rho, mu, dt, g = domain.rho, domain.mu, domain.dt, domain.g
        u, u_1, vu = domain.u, domain.u_1, domain.vu
        p_1 = domain.p_1

        n = FacetNormal(domain.mesh)

        acceleration = rho * inner((u - u_1) / dt, vu) * dx
        pressure = inner(p_1, div(vu)) * dx - dot(p_1 * n, vu) * ds
        body_force = dot(Constant((0.0, -g))*rho, vu)*dx \
            + dot(Constant((0.0, 0.0)), vu) * ds
        # diffusion = (-inner(mu * (grad(u_1) + grad(u_1).T), grad(vu))*dx
        #               + dot(mu * (grad(u_1) + grad(u_1).T)*n, vu)*ds)  # just fine
        # diffusion = (-inner(mu * (grad(u) + grad(u).T), grad(vu))*dx)  # just fine
        diffusion = (-inner(mu * (grad(u) + grad(u).T), grad(vu)) * dx
                     + dot(mu * (grad(u) + grad(u).T) * n, vu) * ds)  # just fine, but horribly slow in combination with ???  -> not reproducable
        # convection = rho*dot(dot(u, nabla_grad(u_1)), vu) * dx  # no vortices
        # convection = rho*dot(dot(u_1, nabla_grad(u)), vu) * dx  # no vortices
        # convection = dot(div(rho*outer(u_1, u_1)), vu) * dx  # not stable!
        convection = rho * dot(dot(u_1, nabla_grad(u_1)), vu) * dx  # just fine
        F_impl = -acceleration - convection + diffusion + pressure + body_force

        self.a, self.L = lhs(F_impl), rhs(F_impl)
        self.domain = domain
        self.A = assemble(self.a)
        [bc.apply(self.A) for bc in domain.bcu]
        return

    def solve(self, reassemble_A=False):
        bcu = self.domain.bcu
        u_ = self.domain.u_
        # u_k = self.domain.u_k  # deprecated.

        piccard_iterations = 1
        for k in range(piccard_iterations):
            if reassemble_A:
                self.A = assemble(self.a)
                [bc.apply(self.A) for bc in self.domain.bcu]
            b = assemble(self.L)
            [bc.apply(b) for bc in bcu]
            solve(self.A, u_.vector(), b, 'bicgstab', 'hypre_amg')
            # u_k.assign(u_)
        return


class ExplicitTentativeVelocityStep():
    def __init__(self, domain):
        rho, mu, dt, g = domain.rho, domain.mu, domain.dt, domain.g
        u, u_1, p_1, vu = domain.u, domain.u_1, domain.p_1, domain.vu

        n = FacetNormal(domain.mesh)
        acceleration = rho * inner((u - u_1) / dt, vu) * dx
        diffusion = (-inner(mu * (grad(u_1) + grad(u_1).T), grad(vu)) * dx
                     + dot(mu * (grad(u_1) + grad(u_1).T) * n, vu) * ds)
        body_force = dot(Constant((0.0, -g))*rho, vu)*dx \
            + dot(Constant((0.0, 0.0)), vu) * ds
        # diffusion = (mu*inner(grad(u_1), grad(vu))*dx
        #              - mu*dot(nabla_grad(u_1)*n, vu)*ds)  # int. by parts
        pressure = inner(p_1, div(vu)) * dx - dot(p_1 * n, vu) * ds  # int. by parts
        # TODO: what is better?
        # convection = dot(div(rho*outer(u_1, u_1)), vu) * dx  # not stable!
        convection = rho * dot(dot(u_1, nabla_grad(u_1)), vu) * dx
        F_impl = -acceleration - convection + diffusion + pressure + body_force
        self.a, self.L = lhs(F_impl), rhs(F_impl)
        self.domain = domain
        self.A = assemble(self.a)
        [bc.apply(self.A) for bc in domain.bcu]
        return

    def solve(self):
        bcu = self.domain.bcu
        u_ = self.domain.u_

        b = assemble(self.L)
        [bc.apply(b) for bc in bcu]
        solve(self.A, u_.vector(), b, 'bicgstab', 'hypre_amg')
        return


class PressureStep():
    def __init__(self, domain):
        rho, dt = domain.rho, domain.dt
        p, p_1, vp = domain.p, domain.p_1, domain.vp
        p_1, u_ = domain.p_1, domain.u_

        # F = rho/dt * dot(div(u_), vp) * dx + dot(grad(p-p_1), grad(vp)) * dx
        self.a = dot(nabla_grad(p), nabla_grad(vp)) * dx
        self.L = (dot(nabla_grad(p_1), nabla_grad(vp)) * dx
                  - (rho / dt) * div(u_) * vp * dx)
        self.A = assemble(self.a)
        [bc.apply(self.A) for bc in domain.bcp]
        self.domain = domain
        return

    def solve(self):
        bcp = self.domain.bcp
        p_ = self.domain.p_

        b = assemble(self.L)
        [bc.apply(b) for bc in bcp]
        solve(self.A, p_.vector(), b, 'bicgstab', 'hypre_amg')
        return


class VelocityCorrectionStep():
    def __init__(self, domain):
        rho, dt = domain.rho, domain.dt
        u, u_, vu = domain.u, domain.u_, domain.vu
        p_1, p_ = domain.p_1, domain.p_

        self.a = dot(u, vu) * dx
        self.L = dot(u_, vu) * dx - dt / rho * dot(nabla_grad(p_ - p_1), vu) * dx
        self.A = assemble(self.a)
        [bc.apply(self.A) for bc in domain.bcu]
        self.domain = domain
        return

    def solve(self):
        bcu = self.domain.bcu
        u_ = self.domain.u_

        b = assemble(self.L)
        [bc.apply(b) for bc in bcu]
        solve(self.A, u_.vector(), b, 'bicgstab', 'hypre_amg')
        return
