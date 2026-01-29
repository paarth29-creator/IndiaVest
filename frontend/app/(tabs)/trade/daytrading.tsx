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
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import Slider from '@react-native-community/slider';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface Recommendation {
  rank?: number;
  symbol: string;
  name: string;
  current_price_inr: number;
  change_24h: number;
  entry_range: { low: number; high: number };
  stop_loss: number;
  stop_loss_pct: number;
  take_profit: { tp1_1to1: number; tp2_1to2: number; tp3_1to3: number };
  max_position_pct?: number;
  signal_strength?: string;
  suggested_quantity?: number;
  suggested_investment_inr?: number;
  sell_guidance?: { target_time: string; exit_strategy: string };
  expected_profit_loss?: {
    best_case_inr: number;
    expected_inr: number;
    worst_case_inr: number;
    probability_profit: number;
    probability_loss: number;
  };
  reasoning?: string;
}

interface DayTradingData {
  should_trade: boolean;
  confidence: number;
  score: number;
  market_conditions: {
    total_volume_usd: number;
    avg_volatility: number;
    liquid_coins_count: number;
    is_good_hours: boolean;
    ist_time: string;
  };
  top_5_recommendations: Recommendation[];
  reasoning: string;
  extreme_risk_warning: string;
}

interface PersonalizedData {
  summary: {
    capital_input: number;
    total_deployed: number;
    deployment_pct: number;
    positions_count: number;
    expected_yield_range: {
      best_case_inr: number;
      best_case_pct: number;
      expected_inr: number;
      expected_pct: number;
      worst_case_inr: number;
      worst_case_pct: number;
      probability_profit_overall: number;
    };
    allocation_breakdown: Array<{
      symbol: string;
      amount: number;
      pct: number;
    }>;
  };
  recommendations: Recommendation[];
  overall_reasoning: string;
}

export default function DayTradingScreen() {
  const router = useRouter();
  const [data, setData] = useState<DayTradingData | null>(null);
  const [personalizedData, setPersonalizedData] = useState<PersonalizedData | null>(null);
  const [loading, setLoading] = useState(true);
  const [personalizedLoading, setPersonalizedLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedCoin, setSelectedCoin] = useState<string | null>(null);
  
  // Capital input state
  const [capitalInput, setCapitalInput] = useState('');
  const [capitalSlider, setCapitalSlider] = useState(10000);
  const [showPersonalized, setShowPersonalized] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_URL}/api/daytrading/should-trade`);
      const result = await response.json();
      setData(result);
    } catch (error) {
      console.error('Error fetching day trading data:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchPersonalized = async (capital: number) => {
    if (capital <= 0) return;
    
    try {
      setPersonalizedLoading(true);
      const response = await fetch(`${API_URL}/api/daytrading/personalized`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ capital, risk_profile: 'medium' })
      });
      const result = await response.json();
      setPersonalizedData(result);
      setShowPersonalized(true);
    } catch (error) {
      console.error('Error fetching personalized data:', error);
    } finally {
      setPersonalizedLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchData();
    if (showPersonalized && capitalSlider > 0) {
      await fetchPersonalized(capitalSlider);
    }
    setRefreshing(false);
  };

  const handleCapitalSubmit = () => {
    const capital = parseFloat(capitalInput) || capitalSlider;
    if (capital > 0) {
      setCapitalSlider(capital);
      fetchPersonalized(capital);
    }
  };

  const handleSliderChange = (value: number) => {
    setCapitalSlider(Math.round(value));
    setCapitalInput(Math.round(value).toString());
  };

  const formatCurrency = (value: number) => {
    if (value >= 100000) {
      return `₹${(value / 100000).toFixed(2)}L`;
    }
    return `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
  };

  const formatVolume = (value: number) => {
    if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
    if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
    return `$${value.toFixed(0)}`;
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#f59e0b" />
          <Text style={styles.loadingText}>Analyzing markets...</Text>
        </View>
      </SafeAreaView>
    );
  }

  const signalColor = data?.should_trade ? '#10b981' : '#ef4444';

  const renderPersonalizedRecommendation = (rec: Recommendation, index: number) => {
    const isExpanded = selectedCoin === `p_${rec.symbol}`;
    
    return (
      <TouchableOpacity
        key={`personalized_${rec.symbol}`}
        style={styles.personalizedCard}
        onPress={() => setSelectedCoin(isExpanded ? null : `p_${rec.symbol}`)}
      >
        <View style={styles.recHeader}>
          <View style={styles.recInfo}>
            <View style={styles.rankBadge}>
              <Text style={styles.rankText}>#{rec.rank || index + 1}</Text>
            </View>
            <View>
              <Text style={styles.recSymbol}>{rec.symbol}</Text>
              <Text style={styles.recName}>{rec.name}</Text>
            </View>
          </View>
          <View style={styles.recPriceContainer}>
            <Text style={styles.recPrice}>{formatCurrency(rec.current_price_inr)}</Text>
            <Text style={styles.recInvestment}>
              Invest: {formatCurrency(rec.suggested_investment_inr || 0)}
            </Text>
          </View>
        </View>

        {/* Expected Profit/Loss Summary */}
        <View style={styles.profitSummary}>
          <View style={styles.profitItem}>
            <Text style={styles.profitLabel}>Best Case</Text>
            <Text style={[styles.profitValue, { color: '#10b981' }]}>
              +{formatCurrency(rec.expected_profit_loss?.best_case_inr || 0)}
            </Text>
          </View>
          <View style={styles.profitItem}>
            <Text style={styles.profitLabel}>Expected</Text>
            <Text style={[styles.profitValue, { color: (rec.expected_profit_loss?.expected_inr || 0) >= 0 ? '#10b981' : '#ef4444' }]}>
              {(rec.expected_profit_loss?.expected_inr || 0) >= 0 ? '+' : ''}{formatCurrency(rec.expected_profit_loss?.expected_inr || 0)}
            </Text>
          </View>
          <View style={styles.profitItem}>
            <Text style={styles.profitLabel}>Worst Case</Text>
            <Text style={[styles.profitValue, { color: '#ef4444' }]}>
              {formatCurrency(rec.expected_profit_loss?.worst_case_inr || 0)}
            </Text>
          </View>
          <View style={styles.profitItem}>
            <Text style={styles.profitLabel}>Win Prob</Text>
            <Text style={styles.profitValue}>{rec.expected_profit_loss?.probability_profit || 0}%</Text>
          </View>
        </View>

        {isExpanded && (
          <View style={styles.expandedContent}>
            <View style={styles.detailSection}>
              <Text style={styles.detailTitle}>ENTRY STRATEGY</Text>
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Entry Range</Text>
                <Text style={styles.detailValue}>
                  {formatCurrency(rec.entry_range.low)} - {formatCurrency(rec.entry_range.high)}
                </Text>
              </View>
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Quantity</Text>
                <Text style={styles.detailValue}>{rec.suggested_quantity?.toFixed(6)} {rec.symbol}</Text>
              </View>
            </View>

            <View style={styles.detailSection}>
              <Text style={styles.detailTitle}>EXIT STRATEGY</Text>
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Stop Loss</Text>
                <Text style={[styles.detailValue, { color: '#ef4444' }]}>
                  {formatCurrency(rec.stop_loss)} (-{rec.stop_loss_pct}%)
                </Text>
              </View>
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>TP1 (1:1)</Text>
                <Text style={[styles.detailValue, { color: '#10b981' }]}>{formatCurrency(rec.take_profit.tp1_1to1)}</Text>
              </View>
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>TP2 (1:2)</Text>
                <Text style={[styles.detailValue, { color: '#10b981' }]}>{formatCurrency(rec.take_profit.tp2_1to2)}</Text>
              </View>
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Target Time</Text>
                <Text style={styles.detailValue}>{rec.sell_guidance?.target_time || 'Within 4 hours'}</Text>
              </View>
            </View>

            {rec.reasoning && (
              <View style={styles.reasoningSection}>
                <Text style={styles.reasoningTitle}>AI Analysis</Text>
                <Text style={styles.reasoningText}>{rec.reasoning}</Text>
              </View>
            )}
          </View>
        )}

        <View style={styles.expandIndicator}>
          <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={20} color="#6b7280" />
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.headerRow}>
        <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={24} color="#fff" />
        </TouchableOpacity>
        <View style={styles.headerTextContainer}>
          <Text style={styles.headerTitle}>Day Trading</Text>
          <Text style={styles.headerSubtitle}>Crypto Intraday Analysis</Text>
        </View>
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <ScrollView
          style={styles.scrollView}
          contentContainerStyle={styles.content}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#f59e0b" />
          }
        >
          {/* Warning Banner */}
          <View style={styles.warningBanner}>
            <Ionicons name="warning" size={20} color="#f59e0b" />
            <Text style={styles.warningText}>
              EXTREME RISK: 90%+ day traders lose money. Educational/virtual use only.
            </Text>
          </View>

          {/* Capital Input Section */}
          <View style={styles.capitalSection}>
            <Text style={styles.capitalTitle}>Planned Investment Today (INR)</Text>
            <View style={styles.capitalInputRow}>
              <TextInput
                style={styles.capitalInput}
                value={capitalInput}
                onChangeText={setCapitalInput}
                keyboardType="numeric"
                placeholder="Enter amount"
                placeholderTextColor="#6b7280"
              />
              <TouchableOpacity
                style={styles.calculateButton}
                onPress={handleCapitalSubmit}
                disabled={personalizedLoading}
              >
                {personalizedLoading ? (
                  <ActivityIndicator size="small" color="#fff" />
                ) : (
                  <Text style={styles.calculateButtonText}>Get Personalized Advice</Text>
                )}
              </TouchableOpacity>
            </View>
            <View style={styles.sliderContainer}>
              <Slider
                style={styles.slider}
                minimumValue={2000}
                maximumValue={500000}
                step={1000}
                value={capitalSlider}
                onValueChange={handleSliderChange}
                minimumTrackTintColor="#f59e0b"
                maximumTrackTintColor="#2d2d44"
                thumbTintColor="#f59e0b"
              />
              <View style={styles.sliderLabels}>
                <Text style={styles.sliderLabel}>₹2K</Text>
                <Text style={styles.sliderValue}>{formatCurrency(capitalSlider)}</Text>
                <Text style={styles.sliderLabel}>₹5L</Text>
              </View>
            </View>
          </View>

          {/* Personalized Results */}
          {showPersonalized && personalizedData && (
            <View style={styles.personalizedSection}>
              <Text style={styles.sectionTitle}>Full Deployment Plan</Text>
              
              {/* Summary Card */}
              <View style={styles.summaryCard}>
                <View style={styles.summaryRow}>
                  <View style={styles.summaryItem}>
                    <Text style={styles.summaryLabel}>Your Capital</Text>
                    <Text style={styles.summaryValue}>{formatCurrency(personalizedData.summary.capital_input)}</Text>
                  </View>
                  <View style={styles.summaryItem}>
                    <Text style={styles.summaryLabel}>Deployed Today</Text>
                    <Text style={[styles.summaryValue, { color: '#10b981' }]}>{formatCurrency(personalizedData.summary.total_deployed)} ({personalizedData.summary.deployment_pct}%)</Text>
                  </View>
                </View>
                <View style={styles.summaryRow}>
                  <View style={styles.summaryItem}>
                    <Text style={styles.summaryLabel}>Positions</Text>
                    <Text style={styles.summaryValue}>{personalizedData.summary.positions_count} coins</Text>
                  </View>
                  <View style={styles.summaryItem}>
                    <Text style={styles.summaryLabel}>Win Probability</Text>
                    <Text style={styles.summaryValue}>{personalizedData.summary.expected_yield_range.probability_profit_overall}%</Text>
                  </View>
                </View>
                
                {/* Allocation Breakdown */}
                <View style={styles.allocationSection}>
                  <Text style={styles.allocationTitle}>Allocation Breakdown</Text>
                  {personalizedData.summary.allocation_breakdown?.map((alloc, i) => (
                    <View key={i} style={styles.allocationRow}>
                      <Text style={styles.allocationCoin}>{alloc.symbol}</Text>
                      <View style={styles.allocationBarContainer}>
                        <View style={[styles.allocationBar, { width: `${alloc.pct}%` }]} />
                      </View>
                      <Text style={styles.allocationAmount}>{formatCurrency(alloc.amount)} ({alloc.pct}%)</Text>
                    </View>
                  ))}
                </View>
                
                <View style={styles.expectedYield}>
                  <Text style={styles.yieldTitle}>Expected EOD Outcome</Text>
                  <View style={styles.yieldRow}>
                    <Text style={[styles.yieldValue, { color: '#10b981' }]}>
                      Best: +{formatCurrency(personalizedData.summary.expected_yield_range.best_case_inr)} (+{personalizedData.summary.expected_yield_range.best_case_pct}%)
                    </Text>
                    <Text style={styles.yieldValue}>
                      Exp: {personalizedData.summary.expected_yield_range.expected_inr >= 0 ? '+' : ''}{formatCurrency(personalizedData.summary.expected_yield_range.expected_inr)}
                    </Text>
                    <Text style={[styles.yieldValue, { color: '#ef4444' }]}>
                      Worst: {formatCurrency(personalizedData.summary.expected_yield_range.worst_case_inr)} ({personalizedData.summary.expected_yield_range.worst_case_pct}%)
                    </Text>
                  </View>
                </View>
              </View>

              {/* Personalized Recommendations */}
              {personalizedData.recommendations.map((rec, index) => renderPersonalizedRecommendation(rec, index))}

              {/* Overall Reasoning */}
              <View style={styles.reasoningCard}>
                <Text style={styles.reasoningTitle}>Strategy Overview</Text>
                <Text style={styles.reasoningText}>{personalizedData.overall_reasoning}</Text>
              </View>
            </View>
          )}

          {/* Default Market Analysis (when no capital entered) */}
          {!showPersonalized && (
            <>
              {/* Main Decision Card */}
              <View style={[styles.decisionCard, { borderColor: signalColor }]}>
                <Text style={styles.decisionQuestion}>Should I Day Trade Crypto Today?</Text>
                
                <View style={styles.decisionResult}>
                  <View style={[styles.decisionBadge, { backgroundColor: signalColor + '20' }]}>
                    <Ionicons 
                      name={data?.should_trade ? 'checkmark-circle' : 'close-circle'} 
                      size={48} 
                      color={signalColor} 
                    />
                  </View>
                  <Text style={[styles.decisionText, { color: signalColor }]}>
                    {data?.should_trade ? 'YES' : 'NO'}
                  </Text>
                </View>

                <View style={styles.confidenceContainer}>
                  <View style={styles.confidenceHeader}>
                    <Text style={styles.confidenceLabel}>Confidence</Text>
                    <Text style={styles.confidenceValue}>{data?.confidence?.toFixed(0)}%</Text>
                  </View>
                  <View style={styles.confidenceBar}>
                    <View 
                      style={[
                        styles.confidenceFill, 
                        { width: `${data?.confidence || 0}%`, backgroundColor: signalColor }
                      ]} 
                    />
                  </View>
                </View>
              </View>

              {/* Market Conditions */}
              <Text style={styles.sectionTitle}>Market Conditions</Text>
              <View style={styles.conditionsGrid}>
                <View style={styles.conditionCard}>
                  <Ionicons name="bar-chart" size={24} color="#3b82f6" />
                  <Text style={styles.conditionValue}>{formatVolume(data?.market_conditions?.total_volume_usd || 0)}</Text>
                  <Text style={styles.conditionLabel}>24h Volume</Text>
                </View>
                <View style={styles.conditionCard}>
                  <Ionicons name="pulse" size={24} color="#f59e0b" />
                  <Text style={styles.conditionValue}>{data?.market_conditions?.avg_volatility?.toFixed(1)}%</Text>
                  <Text style={styles.conditionLabel}>Avg Volatility</Text>
                </View>
                <View style={styles.conditionCard}>
                  <Ionicons name="water" size={24} color="#10b981" />
                  <Text style={styles.conditionValue}>{data?.market_conditions?.liquid_coins_count}</Text>
                  <Text style={styles.conditionLabel}>Liquid Coins</Text>
                </View>
                <View style={styles.conditionCard}>
                  <Ionicons name="time" size={24} color={data?.market_conditions?.is_good_hours ? '#10b981' : '#ef4444'} />
                  <Text style={styles.conditionValue}>{data?.market_conditions?.ist_time}</Text>
                  <Text style={styles.conditionLabel}>{data?.market_conditions?.is_good_hours ? 'Active' : 'Off-peak'}</Text>
                </View>
              </View>

              {/* General Recommendations (without capital) */}
              <Text style={styles.sectionTitle}>Top Trading Opportunities</Text>
              <Text style={styles.sectionSubtitle}>Enter capital above for personalized position sizes</Text>
              {data?.top_5_recommendations?.map((coin, index) => (
                <TouchableOpacity
                  key={coin.symbol}
                  style={styles.coinCard}
                  onPress={() => setSelectedCoin(selectedCoin === coin.symbol ? null : coin.symbol)}
                >
                  <View style={styles.coinHeader}>
                    <View style={styles.coinInfo}>
                      <View style={styles.coinRank}>
                        <Text style={styles.coinRankText}>#{index + 1}</Text>
                      </View>
                      <View>
                        <Text style={styles.coinSymbol}>{coin.symbol}</Text>
                        <Text style={styles.coinName}>{coin.name}</Text>
                      </View>
                    </View>
                    <View style={styles.coinPriceContainer}>
                      <Text style={styles.coinPrice}>{formatCurrency(coin.current_price_inr)}</Text>
                      <View style={[
                        styles.signalBadge,
                        { backgroundColor: coin.signal_strength === 'strong' ? '#10b98120' : '#f59e0b20' }
                      ]}>
                        <Text style={[
                          styles.signalText,
                          { color: coin.signal_strength === 'strong' ? '#10b981' : '#f59e0b' }
                        ]}>
                          {coin.signal_strength?.toUpperCase() || 'MODERATE'}
                        </Text>
                      </View>
                    </View>
                  </View>

                  {selectedCoin === coin.symbol && (
                    <View style={styles.coinDetails}>
                      <View style={styles.detailRow}>
                        <Text style={styles.detailLabel}>Entry Range</Text>
                        <Text style={styles.detailValue}>
                          {formatCurrency(coin.entry_range.low)} - {formatCurrency(coin.entry_range.high)}
                        </Text>
                      </View>
                      <View style={styles.detailRow}>
                        <Text style={styles.detailLabel}>Stop Loss</Text>
                        <Text style={[styles.detailValue, { color: '#ef4444' }]}>
                          {formatCurrency(coin.stop_loss)} (-{coin.stop_loss_pct}%)
                        </Text>
                      </View>
                      <View style={styles.detailRow}>
                        <Text style={styles.detailLabel}>Take Profit (1:2)</Text>
                        <Text style={[styles.detailValue, { color: '#10b981' }]}>
                          {formatCurrency(coin.take_profit.tp2_1to2)}
                        </Text>
                      </View>
                    </View>
                  )}
                  <View style={styles.expandIndicator}>
                    <Ionicons 
                      name={selectedCoin === coin.symbol ? 'chevron-up' : 'chevron-down'} 
                      size={20} 
                      color="#6b7280" 
                    />
                  </View>
                </TouchableOpacity>
              ))}
            </>
          )}

          {/* Disclaimer */}
          <View style={styles.disclaimerCard}>
            <Ionicons name="alert-circle" size={20} color="#ef4444" />
            <Text style={styles.disclaimerText}>
              This is NOT financial advice. 30% VDA tax applies to all crypto gains in India. 
              Virtual/educational use only. Never invest money you cannot afford to lose.
            </Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#2d2d44',
  },
  backButton: {
    padding: 8,
    marginRight: 8,
  },
  headerTextContainer: {
    flex: 1,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#fff',
  },
  headerSubtitle: {
    fontSize: 12,
    color: '#9ca3af',
    marginTop: 2,
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
  warningBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    padding: 12,
    borderRadius: 12,
    marginBottom: 16,
  },
  warningText: {
    color: '#f59e0b',
    fontSize: 12,
    fontWeight: '600',
    marginLeft: 8,
    flex: 1,
  },
  capitalSection: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#f59e0b40',
  },
  capitalTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
  },
  capitalInputRow: {
    flexDirection: 'row',
    gap: 12,
  },
  capitalInput: {
    flex: 1,
    backgroundColor: '#0f0f23',
    borderRadius: 12,
    padding: 14,
    color: '#fff',
    fontSize: 16,
  },
  calculateButton: {
    backgroundColor: '#f59e0b',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    justifyContent: 'center',
  },
  calculateButtonText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 12,
  },
  sliderContainer: {
    marginTop: 16,
  },
  slider: {
    width: '100%',
    height: 40,
  },
  sliderLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sliderLabel: {
    color: '#6b7280',
    fontSize: 12,
  },
  sliderValue: {
    color: '#f59e0b',
    fontSize: 16,
    fontWeight: '700',
  },
  personalizedSection: {
    marginBottom: 20,
  },
  summaryCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  summaryItem: {
    flex: 1,
  },
  summaryLabel: {
    color: '#6b7280',
    fontSize: 12,
  },
  summaryValue: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
    marginTop: 4,
  },
  expectedYield: {
    backgroundColor: '#0f0f23',
    borderRadius: 12,
    padding: 12,
    marginTop: 8,
  },
  yieldTitle: {
    color: '#9ca3af',
    fontSize: 12,
    marginBottom: 8,
  },
  yieldRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  yieldValue: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  allocationSection: {
    marginTop: 12,
    marginBottom: 8,
  },
  allocationTitle: {
    color: '#9ca3af',
    fontSize: 12,
    marginBottom: 8,
  },
  allocationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
  },
  allocationCoin: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
    width: 50,
  },
  allocationBarContainer: {
    flex: 1,
    height: 8,
    backgroundColor: '#2d2d44',
    borderRadius: 4,
    marginHorizontal: 8,
    overflow: 'hidden',
  },
  allocationBar: {
    height: '100%',
    backgroundColor: '#f59e0b',
    borderRadius: 4,
  },
  allocationAmount: {
    color: '#9ca3af',
    fontSize: 11,
    width: 100,
    textAlign: 'right',
  },
  personalizedCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#f59e0b40',
  },
  recHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  recInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  rankBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#f59e0b20',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  rankText: {
    color: '#f59e0b',
    fontSize: 12,
    fontWeight: '700',
  },
  recSymbol: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  recName: {
    color: '#6b7280',
    fontSize: 12,
  },
  recPriceContainer: {
    alignItems: 'flex-end',
  },
  recPrice: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  recInvestment: {
    color: '#f59e0b',
    fontSize: 12,
    marginTop: 2,
  },
  profitSummary: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#2d2d44',
  },
  profitItem: {
    alignItems: 'center',
  },
  profitLabel: {
    color: '#6b7280',
    fontSize: 10,
  },
  profitValue: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
    marginTop: 2,
  },
  expandedContent: {
    marginTop: 16,
  },
  detailSection: {
    backgroundColor: '#0f0f23',
    borderRadius: 12,
    padding: 12,
    marginBottom: 12,
  },
  detailTitle: {
    color: '#f59e0b',
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 8,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  detailLabel: {
    color: '#6b7280',
    fontSize: 13,
  },
  detailValue: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '500',
  },
  reasoningSection: {
    backgroundColor: '#0f0f23',
    borderRadius: 12,
    padding: 12,
  },
  reasoningTitle: {
    color: '#8b5cf6',
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 8,
  },
  reasoningText: {
    color: '#d1d5db',
    fontSize: 12,
    lineHeight: 18,
  },
  expandIndicator: {
    alignItems: 'center',
    marginTop: 8,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 8,
  },
  sectionSubtitle: {
    fontSize: 12,
    color: '#6b7280',
    marginBottom: 12,
  },
  decisionCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 24,
    borderWidth: 2,
    marginBottom: 24,
    alignItems: 'center',
  },
  decisionQuestion: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 20,
    textAlign: 'center',
  },
  decisionResult: {
    alignItems: 'center',
    marginBottom: 20,
  },
  decisionBadge: {
    width: 80,
    height: 80,
    borderRadius: 40,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
  },
  decisionText: {
    fontSize: 36,
    fontWeight: '700',
  },
  confidenceContainer: {
    width: '100%',
  },
  confidenceHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  confidenceLabel: {
    color: '#9ca3af',
    fontSize: 14,
  },
  confidenceValue: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  confidenceBar: {
    height: 8,
    backgroundColor: '#2d2d44',
    borderRadius: 4,
    overflow: 'hidden',
  },
  confidenceFill: {
    height: '100%',
    borderRadius: 4,
  },
  conditionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  conditionCard: {
    width: '48%',
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginBottom: 12,
  },
  conditionValue: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
    marginTop: 8,
  },
  conditionLabel: {
    color: '#6b7280',
    fontSize: 12,
    marginTop: 4,
  },
  coinCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  coinHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  coinInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  coinRank: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#f59e0b20',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  coinRankText: {
    color: '#f59e0b',
    fontSize: 12,
    fontWeight: '700',
  },
  coinSymbol: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  coinName: {
    color: '#6b7280',
    fontSize: 12,
  },
  coinPriceContainer: {
    alignItems: 'flex-end',
  },
  coinPrice: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  signalBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
    marginTop: 4,
  },
  signalText: {
    fontSize: 10,
    fontWeight: '700',
  },
  coinDetails: {
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#2d2d44',
  },
  reasoningCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginTop: 12,
  },
  disclaimerCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    borderRadius: 12,
    padding: 16,
    marginTop: 20,
  },
  disclaimerText: {
    color: '#ef4444',
    fontSize: 12,
    marginLeft: 12,
    flex: 1,
    lineHeight: 18,
  },
});
