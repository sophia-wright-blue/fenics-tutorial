from __future__ import print_function
from fenics import *
import numpy as np

class Solver(object):
    def __init__(self, problem, debug=False):
        self.mesh, degree = problem.mesh_degree()
        self.V = V = FunctionSpace(self.mesh, 'P', degree)
        Dirichlet_cond = problem.Dirichlet_conditions()
        if isinstance(Dirichlet_cond, (Expression)):
            # Just one Expression for Dirichlet conditions on
            # the entire boundary
            self.bcs = [DirichletBC(
                V, Dirichlet_cond,
                lambda x, on_boundary: on_boundary)]
        else:
            # Boundary SubDomain markers
            self.bcs = [
                DirichletBC(V, value, boundaries, index)
                for value, boundaries, index
                in Dirichlet_cond]

        if debug:
            # Print the Dirichlet conditions
            print('No of Dirichlet conditions:', len(self.bcs))
            coor = self.mesh.coordinates()
            d2v = dof_to_vertex_map(V)
            for bc in self.bcs:
                bc_dict = bc.get_boundary_values()
                for dof in bc_dict:
                    print('dof %2d: u=%g' % (dof, bc_dict[dof]))
                    if V.ufl_element().degree() == 1:
                        print('   at point %s' %
                              (str(tuple(coor[d2v[dof]].tolist()))))

        u = TrialFunction(V)
        v = TestFunction(V)
        p = problem.p_coeff()
        self.p = p  # store for flux computations
        f = problem.f_rhs()
        F = dot(p*grad(u), grad(v))*dx
        F -= f*v*dx
        F -= sum([g*v*ds_
                  for g, ds_ in problem.Neumann_conditions()])
        F += sum([r*(u-s)*ds_
                  for r, s, ds_ in problem.Robin_conditions()])
        self.a, self.L = lhs(F), rhs(F)

        if debug and V.dim() < 50:
            A = assemble(self.a)
            print('A:\n', A.array())
            b = assemble(self.L)
            print('b:\n', b.array())

    def solve(self, linear_solver='direct'):
        # Compute solution
        self.u = Function(self.V)

        if linear_solver == 'Krylov':
            solver_parameters = {'linear_solver': 'gmres',
                                 'preconditioner': 'ilu'}
        else:
            solver_parameters = {'linear_solver': 'lu'}

        solve(self.a == self.L, self.u, self.bcs,
              solver_parameters=solver_parameters)
        return self.u

    def flux(self):
        """Compute and return flux -p*grad(u)."""
        mesh = self.u.function_space().mesh()
        degree = self.u.ufl_element().degree()
        V_g = VectorFunctionSpace(mesh, 'P', degree)
        self.flux_u = project(-self.p*grad(self.u), V_g)
        self.flux_u.rename('flux(u)', 'continuous flux field')
        return self.flux_u

class Problem(object):
    """Abstract base class for problems."""
    def solve(self, linear_solver='direct',
              abs_tol=1E-6, rel_tol=1E-5, max_iter=1000):
        self.solver = Solver(self)
        prm = parameters['krylov_solver'] # short form
        prm['absolute_tolerance'] = abs_tol
        prm['relative_tolerance'] = rel_tol
        prm['maximum_iterations'] = max_iter
        return self.solver.solve(linear_solver)

    def solution(self):
        return self.solver.u

    def mesh_degree(self):
        """Return mesh, degree."""
        raise NotImplementedError('Must implement mesh!')

    def p_coeff(self):
        return Constant(1.0)

    def f_rhs(self):
        return Constant(0.0)

    def Dirichlet_conditions(self):
        """Return list of (value,boundary_parts,index) triplets,
        or an Expression (if Dirichlet values only)."""
        return []

    def Neumann_conditions(self):
        """Return list of (g,ds(n)) pairs."""
        return []

    def Robin_conditions(self):
        """Return list of (r,u,ds(n)) triplets."""
        return []


class Problem1(Problem):
    """
    -div(p*grad(u)=f on the unit square.
    General Dirichlet, Neumann, or Robin condition along each
    side. Can have multiple subdomains with p constant in
    each subdomain.
    """
    def __init__(self, Nx, Ny):
        """Initialize mesh, boundary parts, and p."""
        self.mesh = UnitSquareMesh(Nx, Ny)

        tol = 1E-14

        class BoundaryX0(SubDomain):
            def inside(self, x, on_boundary):
                return on_boundary and abs(x[0]) < tol

        class BoundaryX1(SubDomain):
            def inside(self, x, on_boundary):
                return on_boundary and abs(x[0] - 1) < tol

        class BoundaryY0(SubDomain):
            def inside(self, x, on_boundary):
                return on_boundary and abs(x[1]) < tol

        class BoundaryY1(SubDomain):
            def inside(self, x, on_boundary):
                return on_boundary and abs(x[1] - 1) < tol

        # Mark boundaries
        #self.boundary_parts = FacetFunction('size_t', mesh)
        self.boundary_parts = FacetFunction('uint', self.mesh)
        self.boundary_parts.set_all(9999)
        self.bx0 = BoundaryX0()
        self.bx1 = BoundaryX1()
        self.by0 = BoundaryY0()
        self.by1 = BoundaryY1()
        self.bx0.mark(self.boundary_parts, 0)
        self.bx1.mark(self.boundary_parts, 1)
        self.by0.mark(self.boundary_parts, 2)
        self.by1.mark(self.boundary_parts, 3)
        self.ds =  Measure(
            'ds', domain=self.mesh,
            subdomain_data=self.boundary_parts)

        # The domain is the unit square with an embedded rectangle
        class Rectangle(SubDomain):
            def inside(self, x, on_boundary):
                return 0.3 <= x[0] <= 0.7 and 0.3 <= x[1] <= 0.7

        self.materials = CellFunction('size_t', self.mesh)
        self.materials.set_all(0)  # "the rest"
        subdomain = Rectangle()
        subdomain.mark(self.materials, 1)
        self.V0 = FunctionSpace(self.mesh, 'DG', 0)
        self.p = Function(self.V0)
        help = np.asarray(self.materials.array(), dtype=np.int32)
        p_values = [1, 1E-3]
        self.p.vector()[:] = np.choose(help, p_values)

    def mesh_degree(self):
        return self.mesh, 2

    def p_coeff(self):
        return self.p

    def f_rhs(self):
        return Constant(0)

    def Dirichlet_conditions(self):
        """Return list of (value,boundary) pairs."""
        return [(1.0, self.boundary_parts, 2),
                (0.0, self.boundary_parts, 3)]

    def Neumann_conditions(self):
        """Return list of g*ds(n) values."""
        return [(0, self.ds(0)), (0, self.ds(1))]

def demo():
    problem = Problem1(Nx=20, Ny=20)
    problem.solve(linear_solver='direct')
    u = problem.solution()
    u.rename('u', 'potential')  # name 'u' is used in plot
    plot(u)
    flux_u = problem.solver.flux()
    plot(flux_u)
    vtkfile = File('poisson.pvd')
    vtkfile << u
    interactive()

def test_Solver():
    """Recover numerial solution to "machine precision"."""
    class TestProblemExact(Problem):
        def __init__(self, Nx, Ny):
            """Initialize mesh, boundary parts, and p."""
            self.mesh = UnitSquareMesh(Nx, Ny)
            self.u0 = Expression('1 + x[0]*x[0] + 2*x[1]*x[1]')

        def mesh_degree(self):
            return self.mesh, 1

        def f_rhs(self):
            return Constant(-6.0)

        def Dirichlet_conditions(self):
            return self.u0

    problem = TestProblemExact(Nx=2, Ny=2)
    problem.solve(linear_solver='direct')
    u = problem.solution()
    u_e = interpolate(problem.u0, u.function_space())
    max_error = np.abs(u_e.vector().array() -
                       u.vector().array()).max()
    tol = 1E-14
    assert max_error < tol, 'max error: %g' % max_error

if __name__ == '__main__':
    #demo()
    test_Solver()