import {useContext, createContext} from "react";
import type {ReactNode} from "react";
import { useFetcher } from "react-router";

interface LoginResult {
  success: boolean;
  error: string | null;
}

interface SignInRequest {
  email: string,
  password: string
}

interface SignInResponse {
  token: string,
  uuid: string,
  email: string,
  nickname: string
}

export interface AuthContextType {
  token: string | null;
  login: (username: string, password: string) => Promise<LoginResult>;
  logout: () => void;
  isAuthenticated: boolean;
  isLoading: boolean;
  getAuthHeaders: () => Record<string, string>;
}

interface AuthProviderProps {
  children: ReactNode;
  token: string | null;
}

export const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider: React.FC<AuthProviderProps> = ({ children, token }) => {
  const fetcher = useFetcher();
  const isLoading = fetcher.state !== "idle";

  const login = async (username: string, password: string): Promise<LoginResult> => {
    const request: SignInRequest = {email: username, password: password};
    
    try {
      const response = await fetch(`http://localhost:8000/signin`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (response.ok) {
        const data: SignInResponse = await response.json();
        
        const formData = new FormData();
        formData.append('token', data.token);
        formData.append('action', 'login');
        
        fetcher.submit(formData, { 
          method: 'post',
          action: '/auth' 
        });
        
        return { success: true, error: null };
      } else {
        const error = await response.json();
        console.log(error);
        return { success: false, error: error.message || 'Login failed' };
      }
    } catch (error) {
      return { success: false, error: 'Network error' };
    }
  };

  const logout = (): void => {
    const formData = new FormData();
    formData.append('action', 'logout');
    
    fetcher.submit(formData, { 
      method: 'post',
      action: '/auth' 
    });
  };

  const isAuthenticated: boolean = !!token;

  const getAuthHeaders = (): Record<string, string> => {
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  };

  const value: AuthContextType = {
    token,
    login,
    logout,
    isAuthenticated,
    isLoading,
    getAuthHeaders,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context == null) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
