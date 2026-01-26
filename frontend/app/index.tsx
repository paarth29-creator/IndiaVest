import React, { useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Image, Dimensions } from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '../src/context/AuthContext';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

const { width } = Dimensions.get('window');

export default function LandingPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace('/(tabs)/news');
    }
  }, [isAuthenticated, isLoading]);

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.loadingText}>Loading...</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <View style={styles.header}>
          <View style={styles.logoContainer}>
            <Ionicons name="trending-up" size={48} color="#6366f1" />
          </View>
          <Text style={styles.title}>InvestIQ India</Text>
          <Text style={styles.subtitle}>Smart Investment Guidance</Text>
        </View>

        <View style={styles.features}>
          <View style={styles.featureItem}>
            <Ionicons name="newspaper-outline" size={28} color="#10b981" />
            <View style={styles.featureText}>
              <Text style={styles.featureTitle}>AI News Analysis</Text>
              <Text style={styles.featureDesc}>Real-time market insights</Text>
            </View>
          </View>

          <View style={styles.featureItem}>
            <Ionicons name="analytics-outline" size={28} color="#f59e0b" />
            <View style={styles.featureText}>
              <Text style={styles.featureTitle}>Daily Decisions</Text>
              <Text style={styles.featureDesc}>AI-powered recommendations</Text>
            </View>
          </View>

          <View style={styles.featureItem}>
            <Ionicons name="wallet-outline" size={28} color="#ec4899" />
            <View style={styles.featureText}>
              <Text style={styles.featureTitle}>Portfolio Tracker</Text>
              <Text style={styles.featureDesc}>Track & analyze holdings</Text>
            </View>
          </View>

          <View style={styles.featureItem}>
            <Ionicons name="flask-outline" size={28} color="#8b5cf6" />
            <View style={styles.featureText}>
              <Text style={styles.featureTitle}>Trading Simulator</Text>
              <Text style={styles.featureDesc}>Practice risk-free</Text>
            </View>
          </View>
        </View>

        <View style={styles.inrBadge}>
          <Text style={styles.inrText}>All prices in INR | IST timezone</Text>
        </View>

        <TouchableOpacity
          style={styles.loginButton}
          onPress={() => router.push('/login')}
        >
          <Text style={styles.loginButtonText}>Get Started</Text>
          <Ionicons name="arrow-forward" size={20} color="#fff" />
        </TouchableOpacity>

        <Text style={styles.disclaimer}>
          Educational purposes only. Not financial advice.
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0f0f23',
  },
  loadingText: {
    color: '#fff',
    fontSize: 16,
  },
  content: {
    flex: 1,
    paddingHorizontal: 24,
    justifyContent: 'center',
  },
  header: {
    alignItems: 'center',
    marginBottom: 40,
  },
  logoContainer: {
    width: 80,
    height: 80,
    borderRadius: 20,
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  title: {
    fontSize: 32,
    fontWeight: '700',
    color: '#fff',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#9ca3af',
  },
  features: {
    marginBottom: 32,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
  },
  featureText: {
    marginLeft: 16,
  },
  featureTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  featureDesc: {
    fontSize: 13,
    color: '#9ca3af',
    marginTop: 2,
  },
  inrBadge: {
    alignItems: 'center',
    marginBottom: 24,
  },
  inrText: {
    fontSize: 12,
    color: '#6366f1',
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
  },
  loginButton: {
    backgroundColor: '#6366f1',
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 16,
    borderRadius: 12,
    marginBottom: 16,
  },
  loginButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
    marginRight: 8,
  },
  disclaimer: {
    textAlign: 'center',
    fontSize: 12,
    color: '#6b7280',
  },
});
