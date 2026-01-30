import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  TextInput,
  Modal,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface Decision {
  recommendation: string;
  confidence: number;
  reasoning: string;
  allocations: {
    crypto?: Record<string, number>;
    stocks?: Record<string, number>;
  };
  risks: string[];
  timeline: string;
  what_if_available?: boolean;
}

interface MarketSnapshot {
  btc_price: number;
  btc_rsi: number;
  btc_change: number;
  eth_price: number;
  eth_rsi?: number;
  eth_change: number;
  sol_price?: number;
  sol_change?: number;
  nifty_level: number;
  nifty_change: number;
  inr_usd: number;
  top_stocks?: Record<string, { price: number; change: number }>;
}

const RECOMMENDATION_COLORS: Record<string, string> = {
  Crypto: '#10b981',
  Stocks: '#3b82f6',
  Both: '#8b5cf6',
  Hold: '#f59e0b',
};

const RECOMMENDATION_ICONS: Record<string, string> = {
  Crypto: 'logo-bitcoin',
  Stocks: 'trending-up',
  Both: 'git-branch',
  Hold: 'pause-circle',
};

export default function DecisionScreen() {
  const [decision, setDecision] = useState<Decision | null>(null);
  const [marketSnapshot, setMarketSnapshot] = useState<MarketSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [date, setDate] = useState('');
  const [timeIst, setTimeIst] = useState('');
  const [dataSources, setDataSources] = useState<Record<string, string>>({});
  const [editMode, setEditMode] = useState(false);
  const [showWhatIf, setShowWhatIf] = useState(false);
  
  // Editable values
  const [editedValues, setEditedValues] = useState({
    btc_price: '',
    btc_change: '',
    btc_rsi: '',
    eth_price: '',
    nifty_change: '',
    confidence: '',
  });

  useEffect(() => {
    fetchDecision();
    
    // Auto-refresh every 60 seconds
    const interval = setInterval(() => {
      fetchDecision();
    }, 60000);
    
    return () => clearInterval(interval);
  }, []);

  const fetchDecision = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_URL}/api/decision/today`);
      const data = await response.json();
      setDecision(data.decision);
      setMarketSnapshot(data.market_snapshot);
      setDate(data.date);
      setTimeIst(data.time_ist);
      setDataSources(data.data_sources || {});
      
      // Initialize edited values
      if (data.market_snapshot) {
        setEditedValues({
          btc_price: String(data.market_snapshot.btc_price || ''),
          btc_change: String(data.market_snapshot.btc_change || ''),
          btc_rsi: String(data.market_snapshot.btc_rsi || ''),
          eth_price: String(data.market_snapshot.eth_price || ''),
          nifty_change: String(data.market_snapshot.nifty_change || ''),
          confidence: String(data.decision?.confidence || ''),
        });
      }
    } catch (error) {
      console.error('Error fetching decision:', error);
    } finally {
      setLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchDecision();
    setRefreshing(false);
  };

  const runWhatIfSimulation = async () => {
    try {
      const response = await fetch(`${API_URL}/api/decision/what-if`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          btc_price: parseFloat(editedValues.btc_price) || undefined,
          btc_change: parseFloat(editedValues.btc_change) || undefined,
          btc_rsi: parseFloat(editedValues.btc_rsi) || undefined,
          eth_price: parseFloat(editedValues.eth_price) || undefined,
          nifty_change: parseFloat(editedValues.nifty_change) || undefined,
          confidence: parseFloat(editedValues.confidence) || undefined,
        }),
      });
      const data = await response.json();
      
      if (data.what_if_result) {
        // Update display with simulated values
        setDecision(prev => prev ? {
          ...prev,
          recommendation: data.what_if_result.recommendation,
          confidence: data.what_if_result.confidence,
        } : null);
      }
      
      setShowWhatIf(false);
    } catch (error) {
      console.error('What-if simulation error:', error);
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(value);
  };

  const getDisplayValue = (field: string, originalValue: any) => {
    if (editMode && editedValues[field as keyof typeof editedValues]) {
      return editedValues[field as keyof typeof editedValues];
    }
    return originalValue;
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#6366f1" />
          <Text style={styles.loadingText}>Analyzing markets with real data...</Text>
        </View>
      </SafeAreaView>
    );
  }

  const recommendationColor = RECOMMENDATION_COLORS[decision?.recommendation || 'Hold'];
  const recommendationIcon = RECOMMENDATION_ICONS[decision?.recommendation || 'Hold'];
  const displayConfidence = editMode ? parseFloat(editedValues.confidence) || decision?.confidence : decision?.confidence;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#6366f1" />
        }
      >
        <View style={styles.header}>
          <View style={styles.headerTop}>
            <View>
              <Text style={styles.headerTitle}>Daily Decision</Text>
              <Text style={styles.headerSubtitle}>{date} • {timeIst}</Text>
            </View>
            <View style={styles.headerButtons}>
              <TouchableOpacity 
                style={[styles.editButton, editMode && styles.editButtonActive]}
                onPress={() => setEditMode(!editMode)}
              >
                <Ionicons name="pencil" size={18} color={editMode ? '#fff' : '#9ca3af'} />
              </TouchableOpacity>
              {decision?.what_if_available && (
                <TouchableOpacity 
                  style={styles.whatIfButton}
                  onPress={() => setShowWhatIf(true)}
                >
                  <Ionicons name="flask" size={18} color="#8b5cf6" />
                </TouchableOpacity>
              )}
            </View>
          </View>
        </View>

        {/* Data Sources Banner */}
        <View style={styles.sourcesBanner}>
          <Ionicons name="server" size={14} color="#10b981" />
          <Text style={styles.sourcesText}>
            Real-time data: {dataSources.crypto || 'CoinGecko'} (Crypto) • {dataSources.stocks || 'yfinance'} (Stocks)
          </Text>
        </View>

        {/* Main Recommendation Card */}
        <View style={[styles.recommendationCard, { borderColor: recommendationColor }]}>
          <View style={styles.recommendationHeader}>
            <View style={[styles.recommendationIcon, { backgroundColor: recommendationColor + '20' }]}>
              <Ionicons name={recommendationIcon as any} size={32} color={recommendationColor} />
            </View>
            <View style={styles.recommendationInfo}>
              <Text style={styles.recommendationLabel}>TODAY'S RECOMMENDATION</Text>
              <Text style={[styles.recommendationValue, { color: recommendationColor }]}>
                {decision?.recommendation}
              </Text>
            </View>
          </View>
          <View style={styles.confidenceBar}>
            <View style={styles.confidenceLabel}>
              <Text style={styles.confidenceText}>Confidence</Text>
              {editMode ? (
                <TextInput
                  style={styles.editableInput}
                  value={editedValues.confidence}
                  onChangeText={(val) => setEditedValues(prev => ({ ...prev, confidence: val }))}
                  keyboardType="numeric"
                />
              ) : (
                <Text style={styles.confidenceValue}>{displayConfidence}%</Text>
              )}
            </View>
            <View style={styles.confidenceTrack}>
              <View 
                style={[
                  styles.confidenceFill, 
                  { width: `${displayConfidence || 0}%`, backgroundColor: recommendationColor }
                ]} 
              />
            </View>
          </View>
        </View>

        {/* Edit Mode Indicator */}
        {editMode && (
          <View style={styles.editModeBanner}>
            <Ionicons name="information-circle" size={16} color="#f59e0b" />
            <Text style={styles.editModeBannerText}>
              Edit Mode: Tap any number to modify. Changes are session-only for testing.
            </Text>
          </View>
        )}

        {/* Market Snapshot */}
        <Text style={styles.sectionTitle}>Market Snapshot (Live)</Text>
        <View style={styles.marketGrid}>
          <View style={styles.marketCard}>
            <View style={styles.marketHeader}>
              <Ionicons name="logo-bitcoin" size={20} color="#f7931a" />
              <Text style={styles.marketSymbol}>BTC</Text>
            </View>
            {editMode ? (
              <TextInput
                style={styles.editablePrice}
                value={editedValues.btc_price}
                onChangeText={(val) => setEditedValues(prev => ({ ...prev, btc_price: val }))}
                keyboardType="numeric"
              />
            ) : (
              <Text style={styles.marketPrice}>{formatCurrency(marketSnapshot?.btc_price || 0)}</Text>
            )}
            <View style={styles.marketStats}>
              {editMode ? (
                <TextInput
                  style={[styles.editableSmall, { color: '#10b981' }]}
                  value={editedValues.btc_change}
                  onChangeText={(val) => setEditedValues(prev => ({ ...prev, btc_change: val }))}
                  keyboardType="numeric"
                />
              ) : (
                <Text style={[
                  styles.marketChange,
                  { color: (marketSnapshot?.btc_change || 0) >= 0 ? '#10b981' : '#ef4444' }
                ]}>
                  {(marketSnapshot?.btc_change || 0) >= 0 ? '+' : ''}{marketSnapshot?.btc_change?.toFixed(1)}%
                </Text>
              )}
              <Text style={styles.marketRsi}>RSI: {editMode ? editedValues.btc_rsi : marketSnapshot?.btc_rsi}</Text>
            </View>
          </View>

          <View style={styles.marketCard}>
            <View style={styles.marketHeader}>
              <Ionicons name="diamond" size={20} color="#627eea" />
              <Text style={styles.marketSymbol}>ETH</Text>
            </View>
            {editMode ? (
              <TextInput
                style={styles.editablePrice}
                value={editedValues.eth_price}
                onChangeText={(val) => setEditedValues(prev => ({ ...prev, eth_price: val }))}
                keyboardType="numeric"
              />
            ) : (
              <Text style={styles.marketPrice}>{formatCurrency(marketSnapshot?.eth_price || 0)}</Text>
            )}
            <View style={styles.marketStats}>
              <Text style={[
                styles.marketChange,
                { color: (marketSnapshot?.eth_change || 0) >= 0 ? '#10b981' : '#ef4444' }
              ]}>
                {(marketSnapshot?.eth_change || 0) >= 0 ? '+' : ''}{marketSnapshot?.eth_change?.toFixed(1)}%
              </Text>
              {marketSnapshot?.eth_rsi && (
                <Text style={styles.marketRsi}>RSI: {marketSnapshot.eth_rsi}</Text>
              )}
            </View>
          </View>

          <View style={styles.marketCard}>
            <View style={styles.marketHeader}>
              <Ionicons name="trending-up" size={20} color="#3b82f6" />
              <Text style={styles.marketSymbol}>NIFTY</Text>
            </View>
            <Text style={styles.marketPrice}>{marketSnapshot?.nifty_level?.toLocaleString('en-IN')}</Text>
            <View style={styles.marketStats}>
              {editMode ? (
                <TextInput
                  style={[styles.editableSmall, { color: '#3b82f6' }]}
                  value={editedValues.nifty_change}
                  onChangeText={(val) => setEditedValues(prev => ({ ...prev, nifty_change: val }))}
                  keyboardType="numeric"
                />
              ) : (
                <Text style={[
                  styles.marketChange,
                  { color: (marketSnapshot?.nifty_change || 0) >= 0 ? '#10b981' : '#ef4444' }
                ]}>
                  {(marketSnapshot?.nifty_change || 0) >= 0 ? '+' : ''}{marketSnapshot?.nifty_change?.toFixed(2)}%
                </Text>
              )}
            </View>
          </View>

          <View style={styles.marketCard}>
            <View style={styles.marketHeader}>
              <Ionicons name="cash" size={20} color="#f59e0b" />
              <Text style={styles.marketSymbol}>INR/USD</Text>
            </View>
            <Text style={styles.marketPrice}>{marketSnapshot?.inr_usd?.toFixed(2)}</Text>
          </View>
        </View>

        {/* Allocations */}
        {decision?.recommendation !== 'Hold' && (
          <>
            <Text style={styles.sectionTitle}>Suggested Allocations</Text>
            <View style={styles.allocationContainer}>
              {decision?.allocations?.crypto && Object.keys(decision.allocations.crypto).length > 0 && (
                <View style={styles.allocationSection}>
                  <Text style={styles.allocationTitle}>
                    <Ionicons name="logo-bitcoin" size={16} color="#10b981" /> Crypto
                  </Text>
                  {Object.entries(decision.allocations.crypto).map(([symbol, pct]) => (
                    <View key={symbol} style={styles.allocationItem}>
                      <Text style={styles.allocationSymbol}>{symbol}</Text>
                      <View style={styles.allocationBarContainer}>
                        <View style={[styles.allocationBar, { width: `${pct}%`, backgroundColor: '#10b981' }]} />
                      </View>
                      <Text style={styles.allocationPct}>{pct}%</Text>
                    </View>
                  ))}
                </View>
              )}
              {decision?.allocations?.stocks && Object.keys(decision.allocations.stocks).length > 0 && (
                <View style={styles.allocationSection}>
                  <Text style={styles.allocationTitle}>
                    <Ionicons name="business" size={16} color="#3b82f6" /> Stocks
                  </Text>
                  {Object.entries(decision.allocations.stocks).map(([symbol, pct]) => (
                    <View key={symbol} style={styles.allocationItem}>
                      <Text style={styles.allocationSymbol}>{symbol}</Text>
                      <View style={styles.allocationBarContainer}>
                        <View style={[styles.allocationBar, { width: `${pct}%`, backgroundColor: '#3b82f6' }]} />
                      </View>
                      <Text style={styles.allocationPct}>{pct}%</Text>
                    </View>
                  ))}
                </View>
              )}
            </View>
          </>
        )}

        {/* Reasoning */}
        <Text style={styles.sectionTitle}>Analysis & Reasoning</Text>
        <View style={styles.reasoningCard}>
          <Text style={styles.reasoningText}>{decision?.reasoning}</Text>
        </View>

        {/* Risks */}
        <Text style={styles.sectionTitle}>Key Risks</Text>
        <View style={styles.risksContainer}>
          {decision?.risks?.map((risk, index) => (
            <View key={index} style={styles.riskItem}>
              <Ionicons name="warning" size={16} color="#f59e0b" />
              <Text style={styles.riskText}>{risk}</Text>
            </View>
          ))}
        </View>

        {/* Timeline */}
        <View style={styles.timelineCard}>
          <Ionicons name="time" size={20} color="#8b5cf6" />
          <View style={styles.timelineContent}>
            <Text style={styles.timelineLabel}>Suggested Timeline</Text>
            <Text style={styles.timelineValue}>{decision?.timeline}</Text>
          </View>
        </View>

        {/* Disclaimer */}
        <View style={styles.disclaimerCard}>
          <Ionicons name="alert-circle" size={20} color="#ef4444" />
          <Text style={styles.disclaimerText}>
            IMPORTANT: This is NOT financial advice. AI-generated analysis for educational purposes only. 
            Crypto taxed at 30% VDA + 1% TDS in India. Stock LTCG 10% above Rs 1L. Always DYOR and consult a SEBI-registered advisor.
          </Text>
        </View>
      </ScrollView>

      {/* What-If Modal */}
      <Modal
        visible={showWhatIf}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setShowWhatIf(false)}
      >
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <View style={styles.whatIfModalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>What-If Simulator</Text>
              <TouchableOpacity onPress={() => setShowWhatIf(false)}>
                <Ionicons name="close" size={24} color="#fff" />
              </TouchableOpacity>
            </View>
            
            <Text style={styles.whatIfDescription}>
              Adjust metrics below to see how the recommendation changes.
            </Text>

            <View style={styles.whatIfInputGroup}>
              <Text style={styles.whatIfLabel}>BTC Price (INR)</Text>
              <TextInput
                style={styles.whatIfInput}
                value={editedValues.btc_price}
                onChangeText={(val) => setEditedValues(prev => ({ ...prev, btc_price: val }))}
                keyboardType="numeric"
                placeholder="e.g., 7000000"
                placeholderTextColor="#6b7280"
              />
            </View>

            <View style={styles.whatIfInputGroup}>
              <Text style={styles.whatIfLabel}>BTC 24h Change (%)</Text>
              <TextInput
                style={styles.whatIfInput}
                value={editedValues.btc_change}
                onChangeText={(val) => setEditedValues(prev => ({ ...prev, btc_change: val }))}
                keyboardType="numeric"
                placeholder="e.g., -12 for 12% drop"
                placeholderTextColor="#6b7280"
              />
            </View>

            <View style={styles.whatIfInputGroup}>
              <Text style={styles.whatIfLabel}>BTC RSI</Text>
              <TextInput
                style={styles.whatIfInput}
                value={editedValues.btc_rsi}
                onChangeText={(val) => setEditedValues(prev => ({ ...prev, btc_rsi: val }))}
                keyboardType="numeric"
                placeholder="14-100 (30=oversold, 70=overbought)"
                placeholderTextColor="#6b7280"
              />
            </View>

            <View style={styles.whatIfInputGroup}>
              <Text style={styles.whatIfLabel}>Nifty Change (%)</Text>
              <TextInput
                style={styles.whatIfInput}
                value={editedValues.nifty_change}
                onChangeText={(val) => setEditedValues(prev => ({ ...prev, nifty_change: val }))}
                keyboardType="numeric"
                placeholder="e.g., 2.5"
                placeholderTextColor="#6b7280"
              />
            </View>

            <TouchableOpacity style={styles.runSimButton} onPress={runWhatIfSimulation}>
              <Ionicons name="flask" size={20} color="#fff" />
              <Text style={styles.runSimButtonText}>Run Simulation</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>
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
  },
  loadingText: {
    color: '#9ca3af',
    marginTop: 12,
  },
  scrollView: {
    flex: 1,
  },
  content: {
    padding: 20,
  },
  header: {
    marginBottom: 12,
  },
  headerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: '#fff',
  },
  headerSubtitle: {
    fontSize: 14,
    color: '#9ca3af',
    marginTop: 4,
  },
  headerButtons: {
    flexDirection: 'row',
    gap: 8,
  },
  editButton: {
    padding: 10,
    borderRadius: 12,
    backgroundColor: '#1a1a2e',
  },
  editButtonActive: {
    backgroundColor: '#6366f1',
  },
  whatIfButton: {
    padding: 10,
    borderRadius: 12,
    backgroundColor: '#1a1a2e',
  },
  sourcesBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(16, 185, 129, 0.1)',
    padding: 10,
    borderRadius: 10,
    marginBottom: 16,
  },
  sourcesText: {
    color: '#10b981',
    fontSize: 12,
    marginLeft: 8,
  },
  editModeBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    padding: 12,
    borderRadius: 12,
    marginBottom: 16,
  },
  editModeBannerText: {
    color: '#f59e0b',
    fontSize: 12,
    marginLeft: 8,
    flex: 1,
  },
  recommendationCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 20,
    borderWidth: 2,
    marginBottom: 24,
  },
  recommendationHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 20,
  },
  recommendationIcon: {
    width: 64,
    height: 64,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  recommendationInfo: {
    marginLeft: 16,
  },
  recommendationLabel: {
    fontSize: 12,
    color: '#9ca3af',
    fontWeight: '600',
    letterSpacing: 1,
  },
  recommendationValue: {
    fontSize: 28,
    fontWeight: '700',
    marginTop: 4,
  },
  confidenceBar: {
    marginTop: 8,
  },
  confidenceLabel: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  confidenceText: {
    color: '#9ca3af',
    fontSize: 14,
  },
  confidenceValue: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  confidenceTrack: {
    height: 8,
    backgroundColor: '#2d2d44',
    borderRadius: 4,
    overflow: 'hidden',
  },
  confidenceFill: {
    height: '100%',
    borderRadius: 4,
  },
  editableInput: {
    backgroundColor: '#0f0f23',
    color: '#fff',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    fontSize: 14,
    fontWeight: '600',
    minWidth: 60,
    textAlign: 'right',
  },
  editablePrice: {
    backgroundColor: '#0f0f23',
    color: '#fff',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    fontSize: 18,
    fontWeight: '700',
  },
  editableSmall: {
    backgroundColor: '#0f0f23',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    fontSize: 14,
    fontWeight: '500',
    minWidth: 50,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 12,
  },
  marketGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  marketCard: {
    width: '48%',
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  marketHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  marketSymbol: {
    color: '#fff',
    fontWeight: '600',
    marginLeft: 8,
  },
  marketPrice: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
  marketStats: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 8,
  },
  marketChange: {
    fontSize: 14,
    fontWeight: '500',
  },
  marketRsi: {
    fontSize: 12,
    color: '#6b7280',
  },
  allocationContainer: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 24,
  },
  allocationSection: {
    marginBottom: 16,
  },
  allocationTitle: {
    color: '#fff',
    fontWeight: '600',
    marginBottom: 12,
  },
  allocationItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  allocationSymbol: {
    color: '#9ca3af',
    width: 80,
    fontSize: 14,
  },
  allocationBarContainer: {
    flex: 1,
    height: 8,
    backgroundColor: '#2d2d44',
    borderRadius: 4,
    marginHorizontal: 12,
  },
  allocationBar: {
    height: '100%',
    borderRadius: 4,
  },
  allocationPct: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '500',
    width: 40,
    textAlign: 'right',
  },
  reasoningCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 24,
  },
  reasoningText: {
    color: '#d1d5db',
    fontSize: 14,
    lineHeight: 22,
  },
  risksContainer: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 24,
  },
  riskItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  riskText: {
    color: '#d1d5db',
    fontSize: 14,
    marginLeft: 12,
    flex: 1,
  },
  timelineCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 24,
  },
  timelineContent: {
    marginLeft: 12,
  },
  timelineLabel: {
    fontSize: 12,
    color: '#9ca3af',
  },
  timelineValue: {
    fontSize: 16,
    color: '#fff',
    fontWeight: '600',
    marginTop: 4,
  },
  disclaimerCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#ef444440',
  },
  disclaimerText: {
    color: '#ef4444',
    fontSize: 11,
    marginLeft: 12,
    flex: 1,
    lineHeight: 16,
  },
  // What-If Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    justifyContent: 'flex-end',
  },
  whatIfModalContent: {
    backgroundColor: '#1a1a2e',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 20,
    maxHeight: '80%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  modalTitle: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '700',
  },
  whatIfDescription: {
    color: '#9ca3af',
    fontSize: 14,
    marginBottom: 20,
    lineHeight: 20,
  },
  whatIfInputGroup: {
    marginBottom: 16,
  },
  whatIfLabel: {
    color: '#9ca3af',
    fontSize: 13,
    marginBottom: 8,
  },
  whatIfInput: {
    backgroundColor: '#0f0f23',
    borderRadius: 12,
    padding: 14,
    color: '#fff',
    fontSize: 16,
  },
  runSimButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#8b5cf6',
    paddingVertical: 16,
    borderRadius: 12,
    marginTop: 8,
  },
  runSimButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginLeft: 8,
  },
});
