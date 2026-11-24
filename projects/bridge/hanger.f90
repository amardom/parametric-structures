   SUBROUTINE AssembleBeam(Hanger)
     TYPE(Element_t) :: Hanger
     TYPE(Nodes_t) :: Nodal
     TYPE(ValueList_t), POINTER :: Material, Weight
     REAL(KIND=dp) :: K(12,12), F(12), B(12), Axis(3), L, A, E, D, Q
     INTEGER :: I
     LOGICAL :: Found, Reported = .FALSE.

     CALL GetElementNodes(Nodal, Hanger)
     Axis = [Nodal % x(2)-Nodal % x(1), Nodal % y(2)-Nodal % y(1), Nodal % z(2)-Nodal % z(1)]
     L = SQRT(SUM(Axis**2))
     IF (L <= 0.0_dp) CALL Fatal('BridgeHanger','Hanger has zero length')
     Material => GetMaterial(Hanger)
     Weight => GetBodyForce(Hanger)
     D = GetConstReal(Material,'Thickness')
     E = GetConstReal(Material,'Youngs Modulus')
     Q = GetConstReal(Weight,'Body Force 3',Found)
     A = ACOS(-1.0_dp)*D**2/4
     B = 0.0_dp
     B(1:3) = -Axis/L
     B(7:9) = Axis/L
     DO I=1,12
       K(:,I) = (E*A/L)*B*B(I)
     END DO
     F = 0.0_dp
     F([3,9]) = Q*A*L/2
     CALL DefaultUpdateEquations(K,F)
     IF (.NOT. Reported) THEN
       CALL Info('BridgeHanger','Beam element assembled',Level=3)
       Reported=.TRUE.
     END IF
   END SUBROUTINE AssembleBeam
