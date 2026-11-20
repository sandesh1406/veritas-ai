import './App.css';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '@/contexts/AuthContext';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { AuthPage } from '@/pages/Auth';
import { DashboardLayout } from '@/layouts/DashboardLayout';
import { AnalysisHistory } from '@/pages/AnalysisHistory';
import { AnalysisWorkspace } from '@/pages/AnalysisWorkspace';
import { Dashboard } from '@/pages/Dashboard';
import { ResearchLibrary } from '@/pages/ResearchLibrary';
import { SavedReports } from '@/pages/SavedReports';
import { Settings } from '@/pages/Settings';
import { VerifyDocument } from '@/pages/VerifyDocument';
import { HelpCenter } from '@/pages/HelpCenter';

function App() {
  return <BrowserRouter><AuthProvider><Routes><Route path="/login" element={<AuthPage mode="login" />} /><Route path="/signup" element={<AuthPage mode="signup" />} /><Route path="/forgot-password" element={<AuthPage mode="forgot" />} /><Route path="/reset-password" element={<AuthPage mode="reset" />} /><Route element={<ProtectedRoute />}><Route element={<DashboardLayout />}><Route path="/" element={<Dashboard />} /><Route path="/verify" element={<VerifyDocument />} /><Route path="/workspace/:documentId" element={<AnalysisWorkspace />} /><Route path="/history" element={<AnalysisHistory />} /><Route path="/library" element={<ResearchLibrary />} /><Route path="/reports" element={<SavedReports />} /><Route path="/settings" element={<Settings />} /><Route path="/help" element={<HelpCenter />} /></Route></Route><Route path="*" element={<Navigate to="/" replace />} /></Routes></AuthProvider></BrowserRouter>;
}

export default App;
