import React, { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { peekCharacterInfo, warmCharacterInfo } from '@/lib/characterInfo'
import { useUIStructure, avatarFrameSvg, loreFrameSvg, loreFrameStroke } from '@/lib/uiStructure'
import avatarMira from '../../assets/avatars/avatar_mira.png'
import ProtectionSettings from './settings/ProtectionSettings'
import CharacterInformationSectionItem from './CharacterInformationSectionItem'
import TypedText from './TypedText'
import CharacterInformationTier from './CharacterInformationTier'
import CharacterInformationBar from './CharacterInformationBar'
import CharacterGallery from './CharacterGallery'
import CharacterStats from './CharacterStats'
import CharacterTraining from './CharacterTraining'
import CharacterEntries from './CharacterEntries'
import CharacterTraits from './CharacterTraits'

export default function CharacterInformation({ portraitUrl }) {
  const svgStructure = useUIStructure()
  const [info, setInfo] = useState(() => peekCharacterInfo())
  useEffect(() => {
    let alive = true
    warmCharacterInfo().then((r) => { if (alive && r) setInfo(r) })
    return () => {
      alive = false
      api.characterInfoSeen().catch(() => {}).then(() => warmCharacterInfo())
    }
  }, [])

  const rel = (k) => (info && info.relations && info.relations[k]) || null
  const trainingLabel = info && info.training && info.training.label
    ? String(info.training.label)
    : null
  const character = {
    id: info ? info.id : '…',
    name: (info ? info.name : '…').toUpperCase(),
    knowledge: info ? (trainingLabel || info.version) : '…',
    lore: info ? info.lore : '',
    realations: {
      trust: rel('trust') || { lastProgress: 0, newProgress: 0 },
      intimacy: rel('intimacy') || { lastProgress: 0, newProgress: 0 },
      respect: rel('respect') || { lastProgress: 0, newProgress: 0 },
    },
  }

  return (
    <div className='character-information-main-container'> 
        <div className='character-information-header-container'>
            <div className='character-info-header'>
              <div className='character-info-header-title'> ИМЯ</div>
              <div className='character-info-header-title'> ID</div>
              <div className='character-info-header-title'> ЗНАНИЯ</div>
              <div className='character-info-header-text'> {character.name}</div>
              <div className='character-info-header-text'> {character.id}</div>
              <div className='character-info-header-text'> {character.knowledge}</div>
            </div>
            <div className='character-info-avatar'>
                <img className='character-info-avatar-igm' src={portraitUrl || avatarMira} onError={(e) => { e.currentTarget.src = avatarMira }} alt="avatar" />
            </div>
            <div className='character-info-avatar-frame'>
            
              <div dangerouslySetInnerHTML={{ __html: avatarFrameSvg(svgStructure) }} />


            </div>
           

            <div className='character-info-lore' style={{ '--lore-stroke': loreFrameStroke(svgStructure) || undefined }}>
              <div className='character-info-lore-frame character-info-lore-frame-top' dangerouslySetInnerHTML={{ __html: loreFrameSvg(svgStructure) }} />
              <div className='character-info-lore-frame character-info-lore-frame-mid' />
              <div className='character-info-lore-frame character-info-lore-frame-bottom' dangerouslySetInnerHTML={{ __html: loreFrameSvg(svgStructure) }} />
              <div className='character-info-lore-text'>
                <span className='character-info-lore-text-sizer' aria-hidden='true'>{character.lore}</span>
                <TypedText className='character-info-lore-text-typed' text={character.lore} speed={20} />
              </div>


            </div>
        </div>
        <div className='character-information-list'>
            <CharacterInformationSectionItem title="ОТНОШЕНИЕ" defaultOpen>
                <div className='character-information-tiers-container'>
                  
                    <CharacterInformationTier
                      title="ДОВЕРИЕ"
                      lastProgress={character.realations.trust.lastProgress}
                      newProgress={character.realations.trust.newProgress}
                      startDelay={900}
                      tier={rel('trust')?.tier || 'I'}
                      label={rel('trust')?.label || ''}
                    />
                     <CharacterInformationTier
                      title="БЛИЗОСТЬ"
                      lastProgress={character.realations.intimacy.lastProgress}
                      newProgress={character.realations.intimacy.newProgress}
                      startDelay={900}
                      tier={rel('intimacy')?.tier || 'I'}
                      label={rel('intimacy')?.label || ''}
                    />
                     <CharacterInformationTier
                      title="УВАЖЕНИЕ"
                      lastProgress={character.realations.respect.lastProgress}
                      newProgress={character.realations.respect.newProgress}
                      startDelay={900}
                      tier={rel('respect')?.tier || 'I'}
                      label={rel('respect')?.label || ''}
                    />
                  


                </div>
            </CharacterInformationSectionItem>
            <CharacterInformationSectionItem title="ХАРАКТЕР">
                <CharacterTraits section={info ? info.character_tab : null} />
            </CharacterInformationSectionItem>
            <CharacterInformationSectionItem title="МЫСЛИ">
                <CharacterEntries section={info ? info.thoughts : null}
                  emptyText="Пока ни одной мысли — они появляются после рефлексии." />
            </CharacterInformationSectionItem>
            <CharacterInformationSectionItem title="ДНЕВНИК">
                <CharacterEntries section={info ? info.diary : null} collapsible pageSize={10}
                  emptyText="Дневник пока пуст — записи появляются после сессий." />
            </CharacterInformationSectionItem>
            <CharacterInformationSectionItem title="ГАЛЕРЕЯ">
                <CharacterGallery />
            </CharacterInformationSectionItem>
            <CharacterInformationSectionItem title="СТАТИСТИКА">
                <CharacterStats stats={info ? info.stats : null} name={info ? info.name : ''} />
            </CharacterInformationSectionItem>
            <CharacterInformationSectionItem title="ПОДГОТОВКА">
                <CharacterTraining training={info ? info.training : null} name={info ? info.name : ''} />
            </CharacterInformationSectionItem>
            <CharacterInformationSectionItem title="НАСТРОЙКИ">
                <div className='character-information-settings'>
                  <ProtectionSettings open={true} />
                </div>
            </CharacterInformationSectionItem>
        </div>

        
    </div>
  )
}
