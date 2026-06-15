import { createContext, useState, useEffect } from 'react';
import axios from 'axios';

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('token') || null);
  const [loading, setLoading] = useState(true);

  // Setup Axios default header
  useEffect(() => {
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      localStorage.setItem('token', token);
      fetchUser();
    } else {
      delete axios.defaults.headers.common['Authorization'];
      localStorage.removeItem('token');
      setUser(null);
      setLoading(false);
    }
  }, [token]);

  const fetchUser = async () => {
    try {
      const response = await axios.get('/api/users/me');
      setUser(response.data);
    } catch (error) {
      console.error('Error fetching user:', error);
      setToken(null);
    } finally {
      setLoading(false);
    }
  };

  const login = async (username, password) => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    
    const response = await axios.post('/api/token', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    });
    
    localStorage.setItem('token', response.data.access_token);
    localStorage.setItem('refresh_token', response.data.refresh_token || '');
    localStorage.setItem('token_type', response.data.token_type || 'bearer');
    
    setToken(response.data.access_token);
    return response.data;
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('token_type');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};
