import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';

import HomePage from './pages/HomePage';
import ConsultationPage from './pages/ConsultationPage';
import HistoryPage from './pages/HistoryPage';
import AboutPage from './pages/AboutPage';
import { WebSocketProvider } from './contexts/WebSocketContext';
import { DocumentTitle } from './components/DocumentTitle';

import './index.css';

function App() {
  return (
    <WebSocketProvider>
      <Router>
        <div className="App">
          <DocumentTitle />
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/consultation" element={<ConsultationPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/about" element={<AboutPage />} />
          </Routes>
          
          {/* Global Toast Notifications */}
          <Toaster
            position="top-right"
            toastOptions={{
              duration: 4000,
              style: {
                background: '#363636',
                color: '#fff',
              },
              success: {
                duration: 3000,
                iconTheme: {
                  primary: '#00A652',
                  secondary: '#fff',
                },
              },
              error: {
                duration: 5000,
                iconTheme: {
                  primary: '#DC3545',
                  secondary: '#fff',
                },
              },
            }}
          />
        </div>
      </Router>
    </WebSocketProvider>
  );
}

export default App;
