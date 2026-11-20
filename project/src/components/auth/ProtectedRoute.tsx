import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

export function AuthLoadingScreen() {
  return <div className="auth-loading"><div className="loading-orbit" /><span>Loading your secure workspace...</span></div>;
}

export function ProtectedRoute() {
  const { session, isLoading } = useAuth();
  const location = useLocation();
  if (isLoading) return <AuthLoadingScreen />;
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}
