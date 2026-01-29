import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface User {
  user_id: string;
  email: string;
  name: string;
  picture?: string;
  capital: number;
  risk_profile: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  devLogin: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // First check for session_id in URL (OAuth callback)
    if (Platform.OS === 'web') {
      const hash = window.location.hash;
      const search = window.location.search;
      let sessionId = null;
      
      console.log('[AUTH] Checking URL for session_id...');
      console.log('[AUTH] Hash:', hash);
      console.log('[AUTH] Search:', search);
      
      if (hash.includes('session_id=')) {
        sessionId = hash.split('session_id=')[1]?.split('&')[0];
        console.log('[AUTH] Found session_id in hash:', sessionId);
      } else if (search.includes('session_id=')) {
        sessionId = search.split('session_id=')[1]?.split('&')[0];
        console.log('[AUTH] Found session_id in search:', sessionId);
      }
      
      if (sessionId) {
        console.log('[AUTH] Processing session_id from OAuth callback...');
        handleSessionId(sessionId).then(() => {
          // Clear the URL after processing
          window.history.replaceState(null, '', window.location.pathname);
        });
        return; // Don't call checkAuth, handleSessionId will set the user
      }
    }
    
    // No OAuth callback, check existing auth
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      console.log('[AUTH] checkAuth: Starting auth check...');
      const token = await AsyncStorage.getItem('session_token');
      console.log('[AUTH] checkAuth: Token from storage:', token ? `found (${token.substring(0, 20)}...)` : 'not found');
      
      if (token) {
        console.log('[AUTH] checkAuth: Verifying token with backend...');
        const response = await fetch(`${BACKEND_URL}/api/auth/me`, {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });
        console.log('[AUTH] checkAuth: Response status:', response.status);
        
        if (response.ok) {
          const userData = await response.json();
          console.log('[AUTH] checkAuth: User authenticated:', userData.name);
          setUser(userData);
        } else {
          console.log('[AUTH] checkAuth: Auth failed (status ' + response.status + '), clearing token');
          await AsyncStorage.removeItem('session_token');
          setUser(null);
        }
      } else {
        console.log('[AUTH] checkAuth: No token found, user not authenticated');
        setUser(null);
      }
    } catch (error) {
      console.error('[AUTH] checkAuth: Error:', error);
      setUser(null);
    } finally {
      console.log('[AUTH] checkAuth: Complete, setting isLoading to false');
      setIsLoading(false);
    }
  };

  const handleSessionId = async (sessionId: string) => {
    try {
      console.log('[AUTH] handleSessionId: Exchanging session_id for token...');
      setIsLoading(true);
      
      const response = await fetch(`${BACKEND_URL}/api/auth/session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ session_id: sessionId }),
      });

      console.log('[AUTH] handleSessionId: Response status:', response.status);

      if (response.ok) {
        const data = await response.json();
        console.log('[AUTH] handleSessionId: Got session_token, saving...');
        console.log('[AUTH] handleSessionId: User data:', data.user?.name);
        
        await AsyncStorage.setItem('session_token', data.session_token);
        console.log('[AUTH] handleSessionId: Token saved to AsyncStorage');
        
        setUser(data.user);
        console.log('[AUTH] handleSessionId: User state updated');
      } else {
        const errorText = await response.text();
        console.error('[AUTH] handleSessionId: Failed to exchange session_id:', errorText);
      }
    } catch (error) {
      console.error('[AUTH] handleSessionId: Error:', error);
    } finally {
      console.log('[AUTH] handleSessionId: Complete, setting isLoading to false');
      setIsLoading(false);
    }
  };

  const login = async () => {
    try {
      const redirectUrl = Platform.OS === 'web'
        ? `${BACKEND_URL}/`
        : Linking.createURL('/');

      const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;

      if (Platform.OS === 'web') {
        window.location.href = authUrl;
      } else {
        const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
        
        if (result.type === 'success' && result.url) {
          const url = result.url;
          let sessionId = null;
          
          if (url.includes('#session_id=')) {
            sessionId = url.split('#session_id=')[1]?.split('&')[0];
          } else if (url.includes('?session_id=')) {
            sessionId = url.split('?session_id=')[1]?.split('&')[0];
          }
          
          if (sessionId) {
            await handleSessionId(sessionId);
          }
        }
      }
    } catch (error) {
      console.error('Login error:', error);
    }
  };

  const logout = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      if (token) {
        await fetch(`${BACKEND_URL}/api/auth/logout`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });
      }
      await AsyncStorage.removeItem('session_token');
      setUser(null);
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const refreshUser = async () => {
    await checkAuth();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
