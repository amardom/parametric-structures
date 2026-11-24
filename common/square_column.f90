   SUBROUTINE AssembleBeam(Column)
     TYPE(Element_t) :: Column
     TYPE(Nodes_t) :: Nodal
     TYPE(ValueList_t), POINTER :: Mat, Weight
     REAL(KIND=dp) :: K(12,12), T(12,12), F(12), B(4,4), S(4,4)
     REAL(KIND=dp) :: L, A, I, Jt, E, G, Side, Nu, Q
     INTEGER :: Pair(2), Bend(4), Node, Offset, P, R
     LOGICAL :: Found, Reported = .FALSE.

     CALL GetElementNodes(Nodal, Column)
     L = Nodal % z(2) - Nodal % z(1)
     IF (L <= 0.0_dp) CALL Fatal('SquareColumn','Columns must run vertically from base to roof')
     Mat => GetMaterial(Column)
     Weight => GetBodyForce(Column)
     Side = GetConstReal(Mat,'Thickness')
     E = GetConstReal(Mat,'Youngs Modulus')
     Nu = GetConstReal(Mat,'Poisson Ratio')
     G = E/(2*(1+Nu))
     A = Side**2
     I = Side**4/12
     Jt = 0.1406_dp*Side**4
     Q = GetConstReal(Weight,'Body Force 3',Found)
     K = 0.0_dp
     F = 0.0_dp
     T = 0.0_dp
     F([1,7]) = Q*A*L/2
     Pair = [1,7]
     K(Pair,Pair) = E*A/L * RESHAPE([1.0_dp,-1.0_dp,-1.0_dp,1.0_dp],[2,2])
     Pair = [4,10]
     K(Pair,Pair) = G*Jt/L * RESHAPE([1.0_dp,-1.0_dp,-1.0_dp,1.0_dp],[2,2])
     B = RESHAPE([12.0_dp,6*L,-12.0_dp,6*L, &
                   6*L,4*L**2,-6*L,2*L**2, &
                  -12.0_dp,-6*L,12.0_dp,-6*L, &
                   6*L,2*L**2,-6*L,4*L**2],[4,4])*E*I/L**3
     Bend = [2,6,8,12]
     K(Bend,Bend) = B
     S = 0.0_dp
     DO P=1,4
       S(P,P)=(-1.0_dp)**(P+1)
     END DO
     Bend = [3,5,9,11]
     K(Bend,Bend) = MATMUL(S,MATMUL(B,S))

     DO Node=0,1
       Offset=6*Node
       T(Offset+1,Offset+3)=1
       T(Offset+2,Offset+1)=1
       T(Offset+3,Offset+2)=1
       T(Offset+4,Offset+6)=-1
       T(Offset+5,Offset+4)=-1
       T(Offset+6,Offset+5)=-1
     END DO
     CALL DefaultUpdateEquations(MATMUL(TRANSPOSE(T),MATMUL(K,T)),MATMUL(TRANSPOSE(T),F))
     IF (.NOT. Reported) THEN
       CALL Info('SquareColumn','Beam element assembled',Level=3)
       Reported=.TRUE.
     END IF
   END SUBROUTINE AssembleBeam
