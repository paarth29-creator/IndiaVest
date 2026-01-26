import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '../src/context/AuthContext';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

export default function LoginScreen() {
  const router = useRouter();
  const { login, isLoading } = useAuth();
  const [showDisclaimer, setShowDisclaimer] = useState(true);

  const handleLogin = async () => {
    await login();
  };

  return (
    <SafeAreaView style={styles.container}>
      <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
        <Ionicons name="arrow-back" size={24} color="#fff" />
      </TouchableOpacity>

      {showDisclaimer ? (
        <View style={styles.content}>
          <View style={styles.iconContainer}>
            <Ionicons name="information-circle" size={64} color="#f59e0b" />
          </View>
          
          <Text style={styles.title}>Important Disclaimer</Text>
          
          <View style={styles.disclaimerCard}>
            <Text style={styles.disclaimerTitle}>Educational Purpose Only</Text>
            <Text style={styles.disclaimerText}>
              This app provides educational information and simulated trading experiences. 
              It does not constitute financial advice.
            </Text>
          </View>

          <View style={styles.disclaimerCard}>
            <Text style={styles.disclaimerTitle}>Indian Regulations</Text>
            <Text style={styles.disclaimerText}>
              Cryptocurrency gains are taxed at 30% (VDA tax) with 1% TDS. 
              Stock LTCG is 10% above Rs. 1 lakh. Always consult a tax professional.
            </Text>
          </View>

          <View style={styles.disclaimerCard}>
            <Text style={styles.disclaimerTitle}>No Real Trading</Text>
            <Text style={styles.disclaimerText}>
              All trades in this app are simulated. We do not facilitate 
              actual buying or selling of any securities or cryptocurrencies.
            </Text>
          </View>

          <TouchableOpacity
            style={styles.agreeButton}
            onPress={() => setShowDisclaimer(false)}
          >
            <Text style={styles.agreeButtonText}>I Understand, Continue</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={styles.content}>
          <View style={styles.iconContainer}>
            <Ionicons name="lock-closed" size={64} color="#6366f1" />
          </View>
          
          <Text style={styles.title}>Welcome</Text>
          <Text style={styles.subtitle}>Sign in to access your investment dashboard</Text>

          <TouchableOpacity
            style={styles.googleButton}
            onPress={handleLogin}
            disabled={isLoading}
          >
            {isLoading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Ionicons name="logo-google" size={24} color="#fff" style={styles.googleIcon} />
                <Text style={styles.googleButtonText}>Continue with Google</Text>
              </>
            )}
          </TouchableOpacity>

          <Text style={styles.termsText}>
            By continuing, you agree to our Terms of Service and Privacy Policy
          </Text>
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
  },
  backButton: {
    padding: 16,
  },
  content: {
    flex: 1,
    paddingHorizontal: 24,
    justifyContent: 'center',
  },
  iconContainer: {
    alignItems: 'center',
    marginBottom: 24,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: '#fff',
    textAlign: 'center',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#9ca3af',
    textAlign: 'center',
    marginBottom: 40,
  },
  disclaimerCard: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 16,
    borderRadius: 12,
    marginBottom: 16,
  },
  disclaimerTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 8,
  },
  disclaimerText: {
    fontSize: 14,
    color: '#9ca3af',
    lineHeight: 20,
  },
  agreeButton: {
    backgroundColor: '#f59e0b',
    paddingVertical: 16,
    borderRadius: 12,
    marginTop: 16,
  },
  agreeButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    textAlign: 'center',
  },
  googleButton: {
    backgroundColor: '#4285f4',
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 16,
    borderRadius: 12,
  },
  googleIcon: {
    marginRight: 12,
  },
  googleButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  termsText: {
    textAlign: 'center',
    fontSize: 12,
    color: '#6b7280',
    marginTop: 24,
    paddingHorizontal: 20,
  },
});
