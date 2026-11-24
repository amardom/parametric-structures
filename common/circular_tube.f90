   SUBROUTINE AssembleBeam(Column)
     TYPE(Element_t) :: Column
     TYPE(Nodes_t) :: Nodal
     TYPE(ValueList_t), POINTER :: Mat, Weight
     REAL(KIND=dp) :: K(12,12), T(12,12), F(12), B(4,4), S(4,4)
     REAL(KIND=dp) :: L, A, Jt, E, G, Side, Nu, Q, Pi, Inner, Width, Web, Iz, Iy, MedianWidth, MedianDepth
     REAL(KIND=dp) :: Axis(3), Ref(3), LocalY(3), LocalZ(3), Basis(3,3)
     INTEGER :: Pair(2), Bend(4), Node, Offset, P
     LOGICAL :: Found, Reported = .FALSE.

     CALL GetElementNodes(Nodal, Column)
     Axis = [Nodal % x(2)-Nodal % x(1), Nodal % y(2)-Nodal % y(1), Nodal % z(2)-Nodal % z(1)]
     L = SQRT(SUM(Axis**2))
     IF (L <= 0.0_dp) CALL Fatal('CircularTube','Beam has zero length')
     Axis = Axis/L
     Ref = [0.0_dp, 0.0_dp, 1.0_dp]
     IF (ABS(Axis(3)) > 0.9_dp) Ref = [0.0_dp, 1.0_dp, 0.0_dp]
     LocalZ = [Axis(2)*Ref(3)-Axis(3)*Ref(2), Axis(3)*Ref(1)-Axis(1)*Ref(3), Axis(1)*Ref(2)-Axis(2)*Ref(1)]
     LocalZ = LocalZ/SQRT(SUM(LocalZ**2))
     LocalY = [LocalZ(2)*Axis(3)-LocalZ(3)*Axis(2), LocalZ(3)*Axis(1)-LocalZ(1)*Axis(3), &
               LocalZ(1)*Axis(2)-LocalZ(2)*Axis(1)]
     Basis(1,:) = Axis
     Basis(2,:) = LocalY
     Basis(3,:) = LocalZ
     Mat => GetMaterial(Column)
     Weight => GetBodyForce(Column)
     Side = GetConstReal(Mat,'Thickness')
     E = GetConstReal(Mat,'Youngs Modulus')
     Nu = GetConstReal(Mat,'Poisson Ratio')
     G = E/(2*(1+Nu))
     Web = GetConstReal(Mat,'Beam Wall Thickness')
     Width = GetConstReal(Mat,'Beam Section Width',Found)
     IF (Found) THEN
       A = Side*Width - (Side-2*Web)*(Width-2*Web)
       Iz = (Width*Side**3 - (Width-2*Web)*(Side-2*Web)**3)/12
       Iy = (Side*Width**3 - (Side-2*Web)*(Width-2*Web)**3)/12
       MedianWidth = Width-Web
       MedianDepth = Side-Web
       Jt = 2*Web*(MedianWidth*MedianDepth)**2/(MedianWidth+MedianDepth)
     ELSE
       Pi = ACOS(-1.0_dp)
       Inner = Side-2*Web
       A = Pi*(Side**2-Inner**2)/4
       Iz = Pi*(Side**4-Inner**4)/64
       Iy = Iz
       Jt = 2*Iz
     END IF
     Q = GetConstReal(Weight,'Body Force 3',Found)
     K = 0.0_dp
     F = 0.0_dp
     T = 0.0_dp
     F(1:3) = Q*A*L/2*Basis(:,3)
     F(7:9) = F(1:3)
     F(5) = -Q*A*L**2/12*Basis(3,3)
     F(6) = Q*A*L**2/12*Basis(2,3)
     F(11:12) = -F(5:6)
     Pair = [1,7]
     K(Pair,Pair) = E*A/L * RESHAPE([1.0_dp,-1.0_dp,-1.0_dp,1.0_dp],[2,2])
     Pair = [4,10]
     K(Pair,Pair) = G*Jt/L * RESHAPE([1.0_dp,-1.0_dp,-1.0_dp,1.0_dp],[2,2])
     B = RESHAPE([12.0_dp,6*L,-12.0_dp,6*L, &
                   6*L,4*L**2,-6*L,2*L**2, &
                  -12.0_dp,-6*L,12.0_dp,-6*L, &
                   6*L,2*L**2,-6*L,4*L**2],[4,4])*E/L**3
     Bend = [2,6,8,12]
     K(Bend,Bend) = Iz*B
     S = 0.0_dp
     DO P=1,4
       S(P,P)=(-1.0_dp)**(P+1)
     END DO
     Bend = [3,5,9,11]
     K(Bend,Bend) = Iy*MATMUL(S,MATMUL(B,S))

     DO Node=0,1
       Offset=6*Node
       T(Offset+1:Offset+3,Offset+1:Offset+3) = Basis
       T(Offset+4:Offset+6,Offset+4:Offset+6) = -Basis
     END DO
     CALL DefaultUpdateEquations(MATMUL(TRANSPOSE(T),MATMUL(K,T)),MATMUL(TRANSPOSE(T),F))
     IF (.NOT. Reported) THEN
       CALL Info('CircularTube','Beam element assembled',Level=3)
       Reported=.TRUE.
     END IF
   END SUBROUTINE AssembleBeam
